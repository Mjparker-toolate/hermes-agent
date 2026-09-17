"""Fleet config schema and validation for the v1 Hermes↔orchestrator glue.

A fleet document is YAML or JSON. Secrets are **names only** (``secrets_ref``);
values never belong in the document. v1 hard-caps ``max_concurrency`` at 5 and
refuses non-loopback callback URLs so a local n8n/ClawHub caller cannot fan
out to paid cloud or an open SSRF sink.

n8n agent-fleets documents (camelCase ``fleetId`` + ``members``) are coerced
into this canonical snake_case shape. Hermes does **not** run n8n's task
graph; it stores members and caps worker / delegate concurrency.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

V1_MAX_CONCURRENCY = 5
DEFAULT_MAX_CONCURRENCY = 5
FLEET_MAX_MEMBERS = 50
FLEET_INSTRUCTION_MAX_LENGTH = 10000
FLEET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
N8N_AGENT_FLEETS_PROTOCOL = "n8n-agent-fleets"
COMBINED_FLEET_ID = "hermes-clawhub-combined"
CLAWHUB_TOOL_PREFIX = "clawhub:"
CURSOR_CLOUD_TOOL_ID = "cursor-cloud"
_EMBEDDED_SECRET_KEYS = frozenset({
    "secret", "token", "password", "api_key", "apikey", "authorization",
    "access_token", "private_key", "client_secret",
})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "ip6-localhost", "ip6-loopback"})

# Worker statuses counted against the concurrency cap.
LIVE_WORKER_STATUSES = frozenset({"pending", "idle", "running", "draining"})
TERMINAL_WORKER_STATUSES = frozenset({"stopped", "failed"})

DEFAULT_WORKER_TEMPLATE = {
    "model": "",
    "provider": "",
    "tools": [],
    "skills": [],
    "role": "leaf",
    "goal": "",
}

DEFAULT_BACKOFF = {
    "initial_seconds": 1.0,
    "max_seconds": 30.0,
    "multiplier": 2.0,
}

DEFAULT_RETRY = {
    "max_attempts": 2,
}

DEFAULT_MEMBER = {
    "agent_id": "",
    "role": "leaf",
    "tools": [],
    "memory_scope": "",
    "lifecycle": "",
}

_ROLE_ALIASES = {
    "leaf": "leaf",
    "specialist": "leaf",
    "orchestrator": "orchestrator",
    "coordinator": "orchestrator",
}

_TOP_ALIASES = {
    "fleetId": "fleet_id",
    "maxConcurrency": "max_concurrency",
    "workerTemplate": "worker_template",
    "webhookCallbackUrl": "webhook_callback_url",
    "secretsRef": "secrets_ref",
    "killSwitch": "kill_switch",
    "coordinatorAgentId": "coordinator_agent_id",
}

_MEMBER_ALIASES = {
    "agentId": "agent_id",
    "memoryScope": "memory_scope",
}

_BACKOFF_ALIASES = {
    "initialSeconds": "initial_seconds",
    "maxSeconds": "max_seconds",
}

_RETRY_ALIASES = {
    "maxAttempts": "max_attempts",
}

# n8n owns the fan-out/fan-in graph; extra keys must not fail Hermes start.
_N8N_IGNORED_KEYS = frozenset({
    "name", "description", "version", "enabled", "graph", "taskGraph",
    "task_graph", "tasks", "edges", "nodes", "projectId", "project_id",
    "coordinator", "metadata", "fanOut", "fanIn", "fan_out", "fan_in",
})

_KNOWN_CONFIG_KEYS = frozenset({
    "fleet_id", "max_concurrency", "worker_template", "webhook_callback_url",
    "secrets_ref", "backoff", "retry", "kill_switch", "replicas",
    "members", "coordinator_agent_id",
})


class FleetConfigError(ValueError):
    """The fleet document is structurally invalid or violates a v1 invariant."""

    def __init__(self, message: str, *, code: str = "invalid_config") -> None:
        super().__init__(message)
        self.code = code


def is_loopback_host(host: str | None) -> bool:
    """True when *host* can only accept same-machine connections."""
    if not host:
        return False
    cleaned = host.strip().lower().strip("[]")
    if cleaned in _LOOPBACK_HOSTS:
        return True
    try:
        return bool(ipaddress.ip_address(cleaned).is_loopback)
    except ValueError:
        return False


def is_loopback_url(url: str) -> bool:
    """True when *url* is http(s) targeting a loopback host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return is_loopback_host(parsed.hostname)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FleetConfigError(f"{label} must be a mapping.")
    return dict(value)


def _optional_str(value: Any, label: str, *, allow_empty: bool = True) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FleetConfigError(f"{label} must be a string.")
    text = value.strip()
    if not text and not allow_empty:
        raise FleetConfigError(f"{label} must be a non-empty string.")
    return text


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
        return items
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FleetConfigError(f"{label} must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _positive_number(value: Any, label: str, *, default: float, minimum: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FleetConfigError(f"{label} must be a number.")
    number = float(value)
    if number < minimum:
        raise FleetConfigError(f"{label} must be >= {minimum}.")
    return number


def _apply_aliases(data: dict[str, Any], aliases: Mapping[str, str], *, label: str) -> dict[str, Any]:
    out = dict(data)
    for src, dest in aliases.items():
        if src not in out:
            continue
        if dest in out and out[dest] != out[src]:
            raise FleetConfigError(f"{label} has conflicting {src} and {dest}.")
        out[dest] = out.pop(src)
    return out


def _normalize_role(raw: str, *, label: str) -> str:
    role = (raw or "leaf").strip().lower()
    mapped = _ROLE_ALIASES.get(role)
    if mapped is None:
        raise FleetConfigError(
            f"{label} must be one of {sorted(_ROLE_ALIASES)} (coordinator/orchestrator, specialist/leaf)."
        )
    return mapped


def _tool_slug(tool: str) -> str:
    text = (tool or "").strip().lower()
    if text.startswith(CLAWHUB_TOOL_PREFIX):
        text = text[len(CLAWHUB_TOOL_PREFIX):]
    return text


def tool_kind(tool: str) -> str:
    """Classify a member/delegate tool id (clawhub install/run, cursor-cloud, other)."""
    slug = _tool_slug(tool)
    if slug in {CURSOR_CLOUD_TOOL_ID, "cursor-cloud-delegate"}:
        return "cursor-cloud"
    if slug in {"clawhub-install", "install"} or slug.endswith("-install") or slug.endswith("/install"):
        return "install"
    if slug in {"clawhub-run", "run"} or slug.endswith("-run") or slug.endswith("/run"):
        return "run"
    if slug in {"clawhub-search", "search"} or slug.endswith("-search"):
        return "search"
    if slug in {"fleet-delegate", "hermes-learn"}:
        return slug
    return "other"


def install_and_run_conflict(tools: list[str] | None) -> bool:
    """True when one turn lists both a ClawHub install tool and a run tool."""
    kinds = {tool_kind(item) for item in (tools or []) if item}
    return "install" in kinds and "run" in kinds


def _forbid_embedded_secrets(document: Mapping[str, Any], *, path: str = "") -> None:
    """Reject credential values anywhere except ``secrets_ref`` names."""
    for key, value in document.items():
        here = f"{path}.{key}" if path else key
        lowered = str(key).lower()
        if lowered in _EMBEDDED_SECRET_KEYS and here != "secrets_ref":
            if isinstance(value, str) and value.strip():
                raise FleetConfigError(
                    f"{here} embeds a secret value; list the env-var name under secrets_ref instead.",
                    code="secrets_embedded",
                )
            if isinstance(value, (dict, list)) and value:
                raise FleetConfigError(
                    f"{here} must not carry secret material; use secrets_ref names only.",
                    code="secrets_embedded",
                )
        if isinstance(value, Mapping):
            _forbid_embedded_secrets(value, path=here)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    _forbid_embedded_secrets(item, path=f"{here}[{index}]")


def coerce_orchestrator_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Fold n8n camelCase / members into canonical Hermes fleet keys."""
    data = _apply_aliases(dict(document), _TOP_ALIASES, label="fleet config")
    for ignored in list(data):
        if ignored in _N8N_IGNORED_KEYS:
            data.pop(ignored)

    template = data.get("worker_template")
    if isinstance(template, Mapping):
        data["worker_template"] = _apply_aliases(dict(template), {}, label="worker_template")

    backoff = data.get("backoff")
    if isinstance(backoff, Mapping):
        data["backoff"] = _apply_aliases(dict(backoff), _BACKOFF_ALIASES, label="backoff")

    retry = data.get("retry")
    if isinstance(retry, Mapping):
        data["retry"] = _apply_aliases(dict(retry), _RETRY_ALIASES, label="retry")

    members = data.get("members")
    if members is not None:
        data["members"] = _coerce_members(members)
    return data


def _default_tools_for_agent(agent_id: str) -> list[str]:
    slug = agent_id.strip().lower()
    if slug in {CURSOR_CLOUD_TOOL_ID, "cursor-cloud-delegate"}:
        return [CURSOR_CLOUD_TOOL_ID]
    if "clawhub" in slug:
        return [
            f"{CLAWHUB_TOOL_PREFIX}clawhub-search",
            f"{CLAWHUB_TOOL_PREFIX}clawhub-install",
            f"{CLAWHUB_TOOL_PREFIX}clawhub-run",
        ]
    return []


def _coerce_members(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise FleetConfigError("members must be a list.")
    if len(raw) > FLEET_MAX_MEMBERS:
        raise FleetConfigError(
            f"members cannot exceed {FLEET_MAX_MEMBERS}.",
            code="invalid_config",
        )
    members: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            agent_id = item.strip()
            if not agent_id:
                raise FleetConfigError(f"members[{index}] must be a non-empty agent id.")
            role = "orchestrator" if index == 0 or agent_id.lower() in {
                "orchestrator", "coordinator",
            } else "leaf"
            members.append({
                "agent_id": agent_id,
                "role": role,
                "tools": _default_tools_for_agent(agent_id),
                "memory_scope": "fleet",
                "lifecycle": "persistent" if role == "orchestrator" else "task",
            })
            continue
        data = _apply_aliases(_require_mapping(item, f"members[{index}]"), _MEMBER_ALIASES, label=f"members[{index}]")
        agent_id = _optional_str(data.get("agent_id"), f"members[{index}].agent_id", allow_empty=False)
        role = _normalize_role(
            _optional_str(data.get("role"), f"members[{index}].role") or (
                "orchestrator" if index == 0 else "leaf"
            ),
            label=f"members[{index}].role",
        )
        tools = _string_list(data.get("tools"), f"members[{index}].tools")
        members.append({
            "agent_id": agent_id,
            "role": role,
            "tools": tools,
            "memory_scope": _optional_str(data.get("memory_scope"), f"members[{index}].memory_scope") or "fleet",
            "lifecycle": _optional_str(data.get("lifecycle"), f"members[{index}].lifecycle") or (
                "persistent" if role == "orchestrator" else "task"
            ),
        })
    return members


def _worker_template(raw: Any) -> dict[str, Any]:
    template = dict(DEFAULT_WORKER_TEMPLATE)
    if raw is None:
        return template
    data = _require_mapping(raw, "worker_template")
    unknown = set(data) - set(DEFAULT_WORKER_TEMPLATE)
    if unknown:
        raise FleetConfigError(
            f"worker_template has unknown keys: {sorted(unknown)}."
        )
    template["model"] = _optional_str(data.get("model"), "worker_template.model")
    template["provider"] = _optional_str(data.get("provider"), "worker_template.provider")
    template["tools"] = _string_list(data.get("tools"), "worker_template.tools")
    template["skills"] = _string_list(data.get("skills"), "worker_template.skills")
    role_raw = _optional_str(data.get("role"), "worker_template.role") or "leaf"
    template["role"] = _normalize_role(role_raw, label="worker_template.role")
    template["goal"] = _optional_str(data.get("goal"), "worker_template.goal")
    return template


def _backoff(raw: Any) -> dict[str, float]:
    data = _require_mapping(raw, "backoff") if raw is not None else {}
    unknown = set(data) - set(DEFAULT_BACKOFF)
    if unknown:
        raise FleetConfigError(f"backoff has unknown keys: {sorted(unknown)}.")
    initial = _positive_number(
        data.get("initial_seconds"), "backoff.initial_seconds",
        default=DEFAULT_BACKOFF["initial_seconds"], minimum=0.1,
    )
    maximum = _positive_number(
        data.get("max_seconds"), "backoff.max_seconds",
        default=DEFAULT_BACKOFF["max_seconds"], minimum=initial,
    )
    multiplier = _positive_number(
        data.get("multiplier"), "backoff.multiplier",
        default=DEFAULT_BACKOFF["multiplier"], minimum=1.0,
    )
    return {
        "initial_seconds": initial,
        "max_seconds": maximum,
        "multiplier": multiplier,
    }


def _retry(raw: Any) -> dict[str, int]:
    data = _require_mapping(raw, "retry") if raw is not None else {}
    unknown = set(data) - set(DEFAULT_RETRY)
    if unknown:
        raise FleetConfigError(f"retry has unknown keys: {sorted(unknown)}.")
    attempts = data.get("max_attempts", DEFAULT_RETRY["max_attempts"])
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise FleetConfigError("retry.max_attempts must be an integer >= 0.")
    if attempts > 8:
        raise FleetConfigError("retry.max_attempts cannot exceed 8 in v1.")
    return {"max_attempts": attempts}


def _secrets_ref(raw: Any) -> list[str]:
    names = _string_list(raw, "secrets_ref")
    for name in names:
        if not SECRET_NAME_RE.fullmatch(name):
            raise FleetConfigError(
                f"secrets_ref entry {name!r} is not an env-var name "
                "(A-Z, digits, underscore; names only, never values).",
                code="secrets_embedded",
            )
        if "=" in name or ":" in name:
            raise FleetConfigError(
                "secrets_ref must be names only — never KEY=value.",
                code="secrets_embedded",
            )
    return names


def _max_concurrency(raw: Any) -> int:
    if raw is None:
        return DEFAULT_MAX_CONCURRENCY
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise FleetConfigError("max_concurrency must be an integer.")
    if raw < 1:
        raise FleetConfigError("max_concurrency must be >= 1.")
    if raw > V1_MAX_CONCURRENCY:
        raise FleetConfigError(
            f"max_concurrency cannot exceed {V1_MAX_CONCURRENCY} in v1.",
            code="concurrency_cap",
        )
    return raw


def parse_delegate_request(document: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a POST /fleet/{{id}}/delegate body (snake or camelCase)."""
    data = _require_mapping(document, "delegate request")
    _forbid_embedded_secrets(data)
    instruction = data.get("instruction")
    if instruction is None:
        instruction = data.get("FLEET_INSTRUCTION")
    instruction = _optional_str(instruction, "instruction", allow_empty=False)
    if len(instruction) > FLEET_INSTRUCTION_MAX_LENGTH:
        raise FleetConfigError(
            f"instruction exceeds {FLEET_INSTRUCTION_MAX_LENGTH} characters.",
            code="invalid_config",
        )
    node_id = _optional_str(
        data.get("node_id", data.get("nodeId", data.get("FLEET_NODE_ID"))),
        "node_id",
    )
    agent_id = _optional_str(
        data.get("agent_id", data.get("agentId", data.get("FLEET_AGENT_ID"))),
        "agent_id",
    )
    tools = _string_list(data.get("tools", data.get("FLEET_TOOLS")), "tools")
    kind = _optional_str(data.get("kind", data.get("FLEET_KIND")), "kind")
    if not kind:
        kinds = {tool_kind(item) for item in tools}
        if CURSOR_CLOUD_TOOL_ID in kinds or "cursor-cloud" in kinds:
            kind = CURSOR_CLOUD_TOOL_ID
        elif "install" in kinds:
            kind = "clawhub-install"
        elif "run" in kinds:
            kind = "clawhub-run"
        elif "search" in kinds:
            kind = "clawhub-search"
        else:
            kind = "fleet-delegate"
    if install_and_run_conflict(tools):
        raise FleetConfigError(
            "Refusing install and run in the same turn; install first, run later.",
            code="install_run_same_turn",
        )
    return {
        "instruction": instruction,
        "node_id": node_id,
        "agent_id": agent_id,
        "tools": tools,
        "kind": kind,
    }


def normalize_fleet_config(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical fleet config dict or raise :class:`FleetConfigError`."""
    data = coerce_orchestrator_document(_require_mapping(document, "fleet config"))
    _forbid_embedded_secrets(data)
    unknown = set(data) - _KNOWN_CONFIG_KEYS
    if unknown:
        raise FleetConfigError(f"Unknown fleet config keys: {sorted(unknown)}.")

    fleet_id = _optional_str(data.get("fleet_id"), "fleet_id", allow_empty=False)
    if not FLEET_ID_RE.fullmatch(fleet_id):
        raise FleetConfigError(
            "fleet_id must be 1-64 chars of [A-Za-z0-9._-] starting with alphanumeric."
        )

    callback = _optional_str(data.get("webhook_callback_url"), "webhook_callback_url")
    if callback and not is_loopback_url(callback):
        raise FleetConfigError(
            "webhook_callback_url must be an http(s) loopback URL in v1 "
            "(127.0.0.1 / localhost / ::1).",
            code="callback_not_loopback",
        )

    kill_switch = data.get("kill_switch", False)
    if not isinstance(kill_switch, bool):
        raise FleetConfigError("kill_switch must be a boolean.")

    members = data.get("members")
    if members is None:
        member_list: list[dict[str, Any]] = []
    else:
        member_list = list(members)

    replicas = data.get("replicas")
    max_concurrency = _max_concurrency(data.get("max_concurrency"))
    if replicas is None:
        replica_count = min(len(member_list), max_concurrency) if member_list else 1
    else:
        if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
            raise FleetConfigError("replicas must be an integer >= 0.")
        replica_count = replicas
    if replica_count > max_concurrency:
        raise FleetConfigError(
            f"replicas ({replica_count}) exceeds max_concurrency ({max_concurrency}).",
            code="concurrency_cap",
        )

    coordinator = _optional_str(data.get("coordinator_agent_id"), "coordinator_agent_id")
    if not coordinator and member_list:
        for member in member_list:
            if member.get("role") == "orchestrator":
                coordinator = str(member["agent_id"])
                break
        if not coordinator:
            coordinator = str(member_list[0]["agent_id"])

    return {
        "fleet_id": fleet_id,
        "max_concurrency": max_concurrency,
        "worker_template": _worker_template(data.get("worker_template")),
        "webhook_callback_url": callback,
        "secrets_ref": _secrets_ref(data.get("secrets_ref")),
        "backoff": _backoff(data.get("backoff")),
        "retry": _retry(data.get("retry")),
        "kill_switch": kill_switch,
        "replicas": replica_count,
        "members": member_list,
        "coordinator_agent_id": coordinator,
    }


def load_fleet_document(text: str, *, source: str = "document") -> dict[str, Any]:
    """Parse YAML or JSON text into a normalized fleet config."""
    stripped = text.strip()
    if not stripped:
        raise FleetConfigError(f"{source} is empty.")
    payload: Any
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - PyYAML is a runtime dep
            raise FleetConfigError(f"{source} is not JSON and PyYAML is unavailable.") from exc
        payload = yaml.safe_load(stripped)
    if not isinstance(payload, Mapping):
        raise FleetConfigError(f"{source} must be a YAML/JSON mapping.")
    return normalize_fleet_config(payload)


def example_fleet_config() -> dict[str, Any]:
    """Canonical example used by docs, the skill template, and tests."""
    return copy.deepcopy({
        "fleet_id": "local-dev",
        "max_concurrency": 3,
        "worker_template": {
            "model": "",
            "provider": "",
            "tools": ["terminal", "file"],
            "skills": ["hermes-fleet"],
            "role": "leaf",
            "goal": "",
        },
        "webhook_callback_url": "http://127.0.0.1:5678/webhook/hermes-fleet",
        "secrets_ref": ["OPENROUTER_API_KEY"],
        "backoff": dict(DEFAULT_BACKOFF),
        "retry": dict(DEFAULT_RETRY),
        "kill_switch": False,
        "replicas": 1,
    })


def combined_fleet_document() -> dict[str, Any]:
    """n8n-shaped sample: fleetId hermes-clawhub-combined + three members."""
    return copy.deepcopy({
        "fleetId": COMBINED_FLEET_ID,
        "maxConcurrency": 3,
        "members": [
            {
                "agentId": "orchestrator",
                "role": "coordinator",
                "tools": [],
                "memoryScope": "fleet",
                "lifecycle": "persistent",
            },
            {
                "agentId": "clawhub-skill-runner",
                "role": "specialist",
                "tools": [
                    f"{CLAWHUB_TOOL_PREFIX}clawhub-search",
                    f"{CLAWHUB_TOOL_PREFIX}clawhub-install",
                    f"{CLAWHUB_TOOL_PREFIX}clawhub-run",
                ],
                "memoryScope": "fleet",
                "lifecycle": "task",
            },
            {
                "agentId": "cursor-cloud-delegate",
                "role": "specialist",
                "tools": [CURSOR_CLOUD_TOOL_ID],
                "memoryScope": "fleet",
                "lifecycle": "task",
            },
        ],
        "webhookCallbackUrl": "http://127.0.0.1:5678/webhook/hermes-fleet",
        "secretsRef": ["OPENROUTER_API_KEY", "FLEET_HTTP_TOKEN"],
        "killSwitch": False,
    })
