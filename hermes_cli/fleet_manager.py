"""Fleet manager: capped worker slots on top of SessionDB + subagent lifecycle.

v1 does **not** invent a process supervisor. Each worker is a Hermes session
(``source='fleet'``). When a parent agent turn is bound, spawn also launches a
leaf via :class:`agent.subagent_lifecycle.SubagentLifecycleService` (the same
host path as ``delegate_task``). HTTP/n8n callers have no parent, so they get
idle session slots the orchestrator can later drive through existing webhook
or cron entry points.

Concurrency defaults to :data:`DEFAULT_MAX_CONCURRENCY` (3) and cannot
exceed :data:`V1_MAX_CONCURRENCY` (5).
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Any, Callable, Mapping, Optional

from hermes_cli.fleet_schema import (
    CURSOR_CLOUD_TOOL_ID,
    LIVE_WORKER_STATUSES,
    V1_MAX_CONCURRENCY,
    FleetConfigError,
    install_and_run_conflict,
    normalize_fleet_config,
    parse_delegate_request,
    tool_kind,
)
from hermes_cli.fleet_store import list_fleet_ids, load_fleet, save_fleet

CallbackFn = Callable[[dict[str, Any]], None]


class FleetError(Exception):
    """Operational fleet failure with a stable ``code`` for the HTTP surface."""

    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class FleetKillSwitchError(FleetError):
    def __init__(self, fleet_id: str) -> None:
        super().__init__(
            f"Fleet {fleet_id!r} has kill_switch=true; start/scale-up refused.",
            code="kill_switch",
            status=403,
        )


class FleetConcurrencyError(FleetError):
    def __init__(self, fleet_id: str, requested: int, cap: int) -> None:
        super().__init__(
            f"Fleet {fleet_id!r} refuses {requested} live workers (cap {cap}, v1 max {V1_MAX_CONCURRENCY}).",
            code="concurrency_cap",
            status=409,
        )


class FleetNotFoundError(FleetError):
    def __init__(self, fleet_id: str) -> None:
        super().__init__(f"Fleet {fleet_id!r} not found.", code="not_found", status=404)


def _now() -> float:
    return time.time()


def _new_worker_id(index: int) -> str:
    return f"w-{index:02d}-{secrets.token_hex(4)}"


def _new_session_id(fleet_id: str, worker_id: str) -> str:
    return f"fleet_{fleet_id}_{worker_id}_{uuid.uuid4().hex[:8]}"


def _live_workers(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        worker for worker in record.get("workers") or []
        if worker.get("status") in LIVE_WORKER_STATUSES
    ]


def _backoff_delay(config: Mapping[str, Any], attempt: int) -> float:
    backoff = config.get("backoff") or {}
    initial = float(backoff.get("initial_seconds") or 1.0)
    maximum = float(backoff.get("max_seconds") or 30.0)
    multiplier = float(backoff.get("multiplier") or 2.0)
    delay = initial * (multiplier ** max(0, attempt - 1))
    return min(delay, maximum)


class SessionBackend:
    """Create/end fleet-tagged Hermes sessions. Tests may substitute a fake."""

    def create(self, session_id: str, *, model: str, fleet_id: str, worker_id: str) -> str:
        raise NotImplementedError

    def end(self, session_id: str, reason: str) -> None:
        raise NotImplementedError


class HermesSessionBackend(SessionBackend):
    """Real :class:`hermes_state.SessionDB` adapter (profile-aware via HERMES_HOME)."""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    def _session_db(self) -> Any:
        if self._db is None:
            from hermes_state import SessionDB
            self._db = SessionDB()
        return self._db

    def create(self, session_id: str, *, model: str, fleet_id: str, worker_id: str) -> str:
        db = self._session_db()
        db.create_session(
            session_id,
            "fleet",
            model=model or None,
            display_name=f"fleet:{fleet_id}:{worker_id}",
            origin_json=json_origin(fleet_id, worker_id),
        )
        return session_id

    def end(self, session_id: str, reason: str) -> None:
        if not session_id:
            return
        self._session_db().end_session(session_id, reason)


class MemorySessionBackend(SessionBackend):
    """In-memory session ids for unit tests that should not open state.db."""

    def __init__(self) -> None:
        self.created: dict[str, dict[str, str]] = {}
        self.ended: dict[str, str] = {}

    def create(self, session_id: str, *, model: str, fleet_id: str, worker_id: str) -> str:
        self.created[session_id] = {
            "model": model, "fleet_id": fleet_id, "worker_id": worker_id, "source": "fleet",
        }
        return session_id

    def end(self, session_id: str, reason: str) -> None:
        self.ended[session_id] = reason


def json_origin(fleet_id: str, worker_id: str) -> str:
    import json
    return json.dumps({"fleet_id": fleet_id, "worker_id": worker_id, "kind": "fleet_worker"})


class SubagentSpawner:
    """Optional wrap of the public subagent lifecycle API. No-op without a parent."""

    def launch(self, worker: Mapping[str, Any], template: Mapping[str, Any]) -> dict[str, Any] | None:
        from agent.subagent_lifecycle import (
            SubagentLaunchRequest,
            SubagentLifecycleError,
            SubagentLifecycleService,
            get_active_subagent_parent,
        )
        parent = get_active_subagent_parent()
        if parent is None:
            return None
        goal = str(template.get("goal") or "").strip() or (
            f"You are fleet worker {worker.get('worker_id')} for {worker.get('fleet_id')}."
        )
        tools = template.get("tools") or None
        allowed = tuple(tools) if tools else None
        try:
            service = SubagentLifecycleService(get_active_subagent_parent)
            handle = service.launch(SubagentLaunchRequest(
                goal=goal,
                role=str(template.get("role") or "leaf"),
                model=str(template.get("model") or "") or None,
                allowed_toolsets=allowed,
                correlation_id=str(worker.get("worker_id") or ""),
                metadata={"fleet_id": worker.get("fleet_id"), "worker_id": worker.get("worker_id")},
            ))
        except SubagentLifecycleError:
            return None
        return handle.to_dict()

    def cancel(self, handle_dict: Mapping[str, Any] | None) -> None:
        if not handle_dict:
            return
        from agent.subagent_lifecycle import (
            SubagentHandle,
            SubagentLifecycleError,
            SubagentLifecycleService,
            get_active_subagent_parent,
        )
        try:
            handle = SubagentHandle.from_dict(handle_dict)
        except SubagentLifecycleError:
            return
        service = SubagentLifecycleService(get_active_subagent_parent)
        service.cancel(handle, reason="fleet stop/drain")


class FleetManager:
    """Create, list, scale, and drain fleets. One process; JSON files on disk."""

    def __init__(
        self,
        *,
        sessions: SessionBackend | None = None,
        spawner: SubagentSpawner | None = None,
        callback: CallbackFn | None = None,
        clock: Callable[[], float] = _now,
    ) -> None:
        self._lock = threading.RLock()
        self._sessions = sessions if sessions is not None else HermesSessionBackend()
        self._spawner = spawner if spawner is not None else SubagentSpawner()
        self._callback = callback
        self._clock = clock

    def start(self, document: Mapping[str, Any]) -> dict[str, Any]:
        config = normalize_fleet_config(document)
        fleet_id = config["fleet_id"]
        with self._lock:
            existing = load_fleet(fleet_id)
            if existing and _live_workers(existing):
                raise FleetError(
                    f"Fleet {fleet_id!r} is already running.",
                    code="already_running",
                    status=409,
                )
            if config["kill_switch"]:
                raise FleetKillSwitchError(fleet_id)
            record = {
                "fleet_id": fleet_id,
                "status": "running",
                "config": config,
                "workers": [],
                "inflight": 0,
                "created_at": self._clock(),
                "updated_at": self._clock(),
            }
            self._scale_locked(record, config["replicas"])
            self._persist(record, event="started")
            return self._public(record)

    def get(self, fleet_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._require(fleet_id)
            self._reconcile_locked(record)
            self._persist(record, event=None)
            return self._public(record)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            summaries = []
            for fleet_id in list_fleet_ids():
                record = load_fleet(fleet_id)
                if record:
                    summaries.append(self._public(record))
            return summaries

    def scale(self, fleet_id: str, *, replicas: int) -> dict[str, Any]:
        if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
            raise FleetError("replicas must be an integer >= 0.", code="invalid_config")
        with self._lock:
            record = self._require(fleet_id)
            config = record["config"]
            if replicas > int(config["max_concurrency"]):
                raise FleetConcurrencyError(fleet_id, replicas, int(config["max_concurrency"]))
            live = len(_live_workers(record))
            if replicas > live and config.get("kill_switch"):
                raise FleetKillSwitchError(fleet_id)
            if record.get("status") == "stopped" and replicas > 0:
                record["status"] = "running"
            self._scale_locked(record, replicas)
            config["replicas"] = replicas
            self._persist(record, event="scaled")
            return self._public(record)

    def stop(self, fleet_id: str, *, drain: bool = True) -> dict[str, Any]:
        with self._lock:
            record = self._require(fleet_id)
            self._scale_locked(record, 0, drain=drain)
            record["status"] = "stopped"
            record["config"]["replicas"] = 0
            record["inflight"] = 0
            self._persist(record, event="stopped")
            return self._public(record)

    def delegate(self, fleet_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        """Accept one n8n specialist turn. Caps inflight; never evals skill text."""
        try:
            parsed = parse_delegate_request(request)
        except FleetConfigError as exc:
            if getattr(exc, "code", "") == "install_run_same_turn":
                raise FleetError(str(exc), code="install_run_same_turn", status=409) from exc
            raise
        tools = list(parsed["tools"])
        with self._lock:
            record = self._require(fleet_id)
            if record.get("status") != "running":
                raise FleetError(
                    f"Fleet {fleet_id!r} is not running.",
                    code="not_running",
                    status=409,
                )
            if record.get("config", {}).get("kill_switch"):
                raise FleetKillSwitchError(fleet_id)
            worker = self._pick_delegate_worker(record, parsed["agent_id"])
            worker_tools = list(worker.get("tools") or []) if worker else []
            effective_tools = tools or worker_tools
            if install_and_run_conflict(effective_tools) and tools:
                raise FleetError(
                    "Refusing install and run in the same turn; install first, run later.",
                    code="install_run_same_turn",
                    status=409,
                )
            cap = min(int(record["config"]["max_concurrency"]), V1_MAX_CONCURRENCY)
            inflight = int(record.get("inflight") or 0)
            if inflight >= cap:
                raise FleetConcurrencyError(fleet_id, inflight + 1, cap)
            record["inflight"] = inflight + 1
            if worker and worker.get("status") == "idle":
                worker["status"] = "running"
                worker["updated_at"] = self._clock()
            self._persist(record, event=None)
            worker_snapshot = dict(worker) if worker else {}

        try:
            result = self._execute_delegate(parsed, worker_snapshot, fleet_id)
        except Exception as exc:
            result = {
                "status": "failed",
                "output": "",
                "error": str(exc) or "delegate_failed",
                "nodeId": parsed["node_id"],
                "agentId": parsed["agent_id"] or worker_snapshot.get("agent_id") or "",
                "fleet_id": fleet_id,
                "worker_id": worker_snapshot.get("worker_id") or "",
                "kind": parsed["kind"],
            }
        finally:
            with self._lock:
                record = self._require(fleet_id)
                record["inflight"] = max(0, int(record.get("inflight") or 0) - 1)
                if worker_snapshot.get("worker_id"):
                    live = self._find_worker(record, str(worker_snapshot["worker_id"]))
                    if live and live.get("status") == "running" and not live.get("subagent_handle"):
                        live["status"] = "idle"
                        live["updated_at"] = self._clock()
                self._persist(record, event=None)
        return result

    def set_kill_switch(self, fleet_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            record = self._require(fleet_id)
            record["config"]["kill_switch"] = bool(enabled)
            self._persist(record, event="kill_switch")
            return self._public(record)

    def mark_worker_failed(self, fleet_id: str, worker_id: str, *, reason: str = "worker_failed") -> dict[str, Any]:
        """Test/ops hook: apply retry/backoff to a live worker."""
        with self._lock:
            record = self._require(fleet_id)
            worker = self._find_worker(record, worker_id)
            if worker is None:
                raise FleetError(
                    f"Worker {worker_id!r} not found in fleet {fleet_id!r}.",
                    code="not_found",
                    status=404,
                )
            self._fail_worker_locked(record, worker, reason)
            self._persist(record, event="worker_failed")
            return self._public(record)

    def _require(self, fleet_id: str) -> dict[str, Any]:
        record = load_fleet(fleet_id)
        if record is None:
            raise FleetNotFoundError(fleet_id)
        return record

    def _scale_locked(self, record: dict[str, Any], target: int, *, drain: bool = True) -> None:
        config = record["config"]
        cap = min(int(config["max_concurrency"]), V1_MAX_CONCURRENCY)
        if target > cap:
            raise FleetConcurrencyError(record["fleet_id"], target, cap)
        live = _live_workers(record)
        while len(live) < target:
            self._spawn_worker_locked(record)
            live = _live_workers(record)
        extras = live[target:]
        for worker in extras:
            self._stop_worker_locked(record, worker, reason="fleet_drain" if drain else "fleet_stop")

    def _next_member(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        members = list((record.get("config") or {}).get("members") or [])
        live_ids = {
            str(worker.get("agent_id") or "")
            for worker in _live_workers(record)
            if worker.get("agent_id")
        }
        for member in members:
            agent_id = str(member.get("agent_id") or "")
            if agent_id and agent_id not in live_ids:
                return dict(member)
        return None

    def _pick_delegate_worker(self, record: Mapping[str, Any], agent_id: str) -> dict[str, Any] | None:
        wanted = (agent_id or "").strip()
        live = _live_workers(record)
        if wanted:
            for worker in live:
                if str(worker.get("agent_id") or "") == wanted:
                    return worker
        for worker in live:
            if worker.get("status") == "idle":
                return worker
        return live[0] if live else None

    def _execute_delegate(
        self,
        parsed: Mapping[str, Any],
        worker: Mapping[str, Any],
        fleet_id: str,
    ) -> dict[str, Any]:
        """Record the turn. Never eval SKILL.md; never call Cursor cloud."""
        kind = str(parsed.get("kind") or "")
        agent_id = str(parsed.get("agent_id") or worker.get("agent_id") or "")
        node_id = str(parsed.get("node_id") or "")
        worker_id = str(worker.get("worker_id") or "")
        if kind == CURSOR_CLOUD_TOOL_ID or tool_kind(kind) == "cursor-cloud":
            output = (
                f"accepted cursor-cloud turn for {agent_id or worker_id} "
                "(not executed; Cloud lane owns Cursor API calls)."
            )
        else:
            output = (
                f"recorded {kind or 'fleet-delegate'} for {agent_id or worker_id}; "
                "ClawHub skill text is untrusted and was not evaluated."
            )
        return {
            "status": "ok",
            "output": output,
            "error": None,
            "nodeId": node_id,
            "agentId": agent_id,
            "fleet_id": fleet_id,
            "worker_id": worker_id,
            "kind": kind,
        }

    def _spawn_worker_locked(self, record: dict[str, Any]) -> dict[str, Any]:
        config = record["config"]
        fleet_id = record["fleet_id"]
        index = len(record["workers"]) + 1
        worker_id = _new_worker_id(index)
        session_id = _new_session_id(fleet_id, worker_id)
        template = dict(config.get("worker_template") or {})
        member = self._next_member(record)
        agent_id = ""
        if member:
            agent_id = str(member.get("agent_id") or "")
            if member.get("tools"):
                template["tools"] = list(member["tools"])
            if member.get("role"):
                template["role"] = member["role"]
        model = str(template.get("model") or "")
        self._sessions.create(
            session_id, model=model, fleet_id=fleet_id, worker_id=worker_id,
        )
        worker = {
            "worker_id": worker_id,
            "fleet_id": fleet_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "role": str(template.get("role") or "leaf"),
            "tools": list(template.get("tools") or []),
            "status": "idle",
            "attempts": 0,
            "next_retry_at": None,
            "subagent_handle": None,
            "error": None,
            "created_at": self._clock(),
            "updated_at": self._clock(),
        }
        handle = self._spawner.launch(worker, template)
        if handle:
            worker["subagent_handle"] = handle
            worker["status"] = "running"
        record["workers"].append(worker)
        return worker

    def _stop_worker_locked(self, record: dict[str, Any], worker: dict[str, Any], *, reason: str) -> None:
        if worker.get("status") not in LIVE_WORKER_STATUSES:
            return
        worker["status"] = "draining"
        worker["updated_at"] = self._clock()
        self._spawner.cancel(worker.get("subagent_handle"))
        session_id = str(worker.get("session_id") or "")
        if session_id:
            self._sessions.end(session_id, reason)
        worker["status"] = "stopped"
        worker["updated_at"] = self._clock()

    def _fail_worker_locked(self, record: dict[str, Any], worker: dict[str, Any], reason: str) -> None:
        config = record["config"]
        attempts = int(worker.get("attempts") or 0) + 1
        worker["attempts"] = attempts
        worker["error"] = reason
        worker["updated_at"] = self._clock()
        max_attempts = int((config.get("retry") or {}).get("max_attempts") or 0)
        if attempts <= max_attempts and not config.get("kill_switch"):
            worker["status"] = "pending"
            worker["next_retry_at"] = self._clock() + _backoff_delay(config, attempts)
            return
        self._spawner.cancel(worker.get("subagent_handle"))
        session_id = str(worker.get("session_id") or "")
        if session_id:
            self._sessions.end(session_id, "fleet_worker_failed")
        worker["status"] = "failed"
        worker["next_retry_at"] = None

    def _reconcile_locked(self, record: dict[str, Any]) -> None:
        """Promote pending retries whose backoff has elapsed, if under cap."""
        if record.get("status") != "running" or record.get("config", {}).get("kill_switch"):
            return
        config = record["config"]
        cap = min(int(config["max_concurrency"]), V1_MAX_CONCURRENCY)
        now = self._clock()
        for worker in record.get("workers") or []:
            if worker.get("status") != "pending":
                continue
            due = worker.get("next_retry_at")
            if due is not None and float(due) > now:
                continue
            live = len(_live_workers(record))
            # pending already counts as live; just flip back to idle/running
            if live > cap:
                continue
            worker["status"] = "idle"
            worker["next_retry_at"] = None
            worker["updated_at"] = now
            handle = self._spawner.launch(worker, config.get("worker_template") or {})
            if handle:
                worker["subagent_handle"] = handle
                worker["status"] = "running"

    def _find_worker(self, record: Mapping[str, Any], worker_id: str) -> Optional[dict[str, Any]]:
        for worker in record.get("workers") or []:
            if worker.get("worker_id") == worker_id:
                return worker
        return None

    def _persist(self, record: dict[str, Any], *, event: str | None) -> None:
        record["updated_at"] = self._clock()
        record["live_workers"] = len(_live_workers(record))
        save_fleet(record)
        if event and self._callback:
            payload = {
                "event": event,
                "fleet": self._public(record),
            }
            self._callback(payload)

    def _public(self, record: Mapping[str, Any]) -> dict[str, Any]:
        workers = list(record.get("workers") or [])
        config = record.get("config") or {}
        return {
            "fleet_id": record.get("fleet_id"),
            "status": record.get("status"),
            "kill_switch": bool(config.get("kill_switch")),
            "max_concurrency": config.get("max_concurrency"),
            "replicas": config.get("replicas"),
            "live_workers": len(_live_workers(record)),
            "inflight": int(record.get("inflight") or 0),
            "coordinator_agent_id": config.get("coordinator_agent_id") or "",
            "members": [dict(m) for m in (config.get("members") or [])],
            "webhook_callback_url": config.get("webhook_callback_url") or "",
            "secrets_ref": list(config.get("secrets_ref") or []),
            "worker_template": dict(config.get("worker_template") or {}),
            "backoff": dict(config.get("backoff") or {}),
            "retry": dict(config.get("retry") or {}),
            "workers": [
                {
                    "worker_id": w.get("worker_id"),
                    "session_id": w.get("session_id"),
                    "agent_id": w.get("agent_id") or "",
                    "role": w.get("role") or "",
                    "tools": list(w.get("tools") or []),
                    "status": w.get("status"),
                    "attempts": w.get("attempts") or 0,
                    "error": w.get("error"),
                    "created_at": w.get("created_at"),
                    "updated_at": w.get("updated_at"),
                }
                for w in workers
            ],
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }


def default_manager() -> FleetManager:
    return FleetManager()
