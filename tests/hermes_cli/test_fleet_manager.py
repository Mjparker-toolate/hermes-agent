"""Concurrency cap and start/scale/stop lifecycle for FleetManager."""

from __future__ import annotations

import pytest

from hermes_cli.fleet_manager import (
    FleetConcurrencyError,
    FleetError,
    FleetKillSwitchError,
    FleetManager,
    FleetNotFoundError,
    HermesSessionBackend,
    MemorySessionBackend,
)
from hermes_cli.fleet_schema import V1_MAX_CONCURRENCY
from hermes_cli.fleet_store import load_fleet, save_fleet
from hermes_state import SessionDB


class _Clock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingSpawner:
    def __init__(self, *, launch_handle=None) -> None:
        self.launches: list[dict] = []
        self.cancels: list[object] = []
        self._handle = launch_handle

    def launch(self, worker, template):
        self.launches.append({"worker": dict(worker), "template": dict(template)})
        return self._handle

    def cancel(self, handle_dict) -> None:
        self.cancels.append(handle_dict)


def _manager(**kwargs) -> FleetManager:
    sessions = kwargs.pop("sessions", MemorySessionBackend())
    spawner = kwargs.pop("spawner", _RecordingSpawner())
    return FleetManager(sessions=sessions, spawner=spawner, **kwargs)


def _start_doc(**overrides):
    doc = {
        "fleet_id": "alpha",
        "max_concurrency": 3,
        "replicas": 2,
        "worker_template": {"tools": ["terminal"], "role": "leaf"},
        "retry": {"max_attempts": 2},
        "backoff": {"initial_seconds": 1.0, "max_seconds": 8.0, "multiplier": 2.0},
    }
    doc.update(overrides)
    return doc


def test_start_creates_idle_session_slots_up_to_replicas(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    sessions = MemorySessionBackend()
    spawner = _RecordingSpawner()
    mgr = _manager(sessions=sessions, spawner=spawner)
    status = mgr.start(_start_doc())

    assert status["status"] == "running"
    assert status["live_workers"] == 2
    assert status["replicas"] == 2
    assert len(sessions.created) == 2
    assert all(meta["source"] == "fleet" for meta in sessions.created.values())
    assert all(worker["status"] == "idle" for worker in status["workers"])
    assert len(spawner.launches) == 2  # attempted; no parent → handle stays None


def test_spawner_handle_marks_worker_running(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spawner = _RecordingSpawner(launch_handle={"task_id": "sa-1", "status": "running"})
    mgr = _manager(spawner=spawner)
    status = mgr.start(_start_doc(replicas=1))
    assert status["workers"][0]["status"] == "running"
    mgr.stop("alpha")
    assert spawner.cancels == [{"task_id": "sa-1", "status": "running"}]


def test_scale_up_and_drain_honor_the_live_set(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    sessions = MemorySessionBackend()
    mgr = _manager(sessions=sessions)
    mgr.start(_start_doc(replicas=1))

    scaled = mgr.scale("alpha", replicas=3)
    assert scaled["live_workers"] == 3
    assert len(sessions.created) == 3

    drained = mgr.scale("alpha", replicas=1)
    assert drained["live_workers"] == 1
    assert len(sessions.ended) == 2
    assert set(sessions.ended.values()) == {"fleet_drain"}

    stopped = mgr.stop("alpha")
    assert stopped["status"] == "stopped"
    assert stopped["live_workers"] == 0
    assert stopped["replicas"] == 0
    assert len(sessions.ended) == 3


def test_scale_above_fleet_cap_is_a_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    mgr.start(_start_doc(max_concurrency=3, replicas=1))
    with pytest.raises(FleetConcurrencyError) as exc:
        mgr.scale("alpha", replicas=4)
    assert exc.value.code == "concurrency_cap"
    assert exc.value.status == 409
    assert mgr.get("alpha")["live_workers"] == 1


def test_v1_ceiling_still_applies_if_stored_cap_is_tampered(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    mgr.start(_start_doc(max_concurrency=5, replicas=1))
    record = load_fleet("alpha")
    assert record is not None
    record["config"]["max_concurrency"] = V1_MAX_CONCURRENCY + 5
    save_fleet(record)

    with pytest.raises(FleetConcurrencyError):
        mgr.scale("alpha", replicas=V1_MAX_CONCURRENCY + 1)
    assert mgr.get("alpha")["live_workers"] == 1


def test_kill_switch_blocks_start_and_scale_up_but_not_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    with pytest.raises(FleetKillSwitchError) as exc:
        mgr.start(_start_doc(kill_switch=True))
    assert exc.value.status == 403

    mgr.start(_start_doc(replicas=2))
    mgr.set_kill_switch("alpha", True)
    with pytest.raises(FleetKillSwitchError):
        mgr.scale("alpha", replicas=3)
    still_live = mgr.scale("alpha", replicas=1)
    assert still_live["live_workers"] == 1
    stopped = mgr.stop("alpha")
    assert stopped["status"] == "stopped"
    assert stopped["live_workers"] == 0


def test_second_start_while_live_is_already_running(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    mgr.start(_start_doc(replicas=1))
    with pytest.raises(FleetError) as exc:
        mgr.start(_start_doc(replicas=1))
    assert exc.value.code == "already_running"
    mgr.stop("alpha")
    restarted = mgr.start(_start_doc(replicas=1))
    assert restarted["status"] == "running"
    assert restarted["live_workers"] == 1


def test_retry_backoff_then_terminal_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    clock = _Clock()
    mgr = _manager(clock=clock)
    status = mgr.start(_start_doc(replicas=1, retry={"max_attempts": 1}))
    worker_id = status["workers"][0]["worker_id"]

    pending = mgr.mark_worker_failed("alpha", worker_id, reason="boom")
    assert pending["workers"][0]["status"] == "pending"
    assert pending["live_workers"] == 1
    assert pending["workers"][0]["attempts"] == 1

    still_pending = mgr.get("alpha")
    assert still_pending["workers"][0]["status"] == "pending"

    clock.advance(2.0)
    recovered = mgr.get("alpha")
    assert recovered["workers"][0]["status"] == "idle"

    failed = mgr.mark_worker_failed("alpha", worker_id, reason="boom-again")
    # attempts=2 > max_attempts=1 → terminal
    assert failed["workers"][0]["status"] == "failed"
    assert failed["live_workers"] == 0


def test_max_attempts_zero_fails_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    status = mgr.start(_start_doc(replicas=1, retry={"max_attempts": 0}))
    worker_id = status["workers"][0]["worker_id"]
    failed = mgr.mark_worker_failed("alpha", worker_id, reason="no-retry")
    assert failed["workers"][0]["status"] == "failed"
    assert failed["live_workers"] == 0


def test_unknown_fleet_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    with pytest.raises(FleetNotFoundError):
        mgr.get("missing")


def test_bool_replicas_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = _manager()
    mgr.start(_start_doc(replicas=1))
    with pytest.raises(FleetError, match="integer"):
        mgr.scale("alpha", replicas=True)  # noqa: FBT003 — the bug class under test


def test_session_backend_creates_fleet_source_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = SessionDB(tmp_path / "state.db")
    try:
        backend = HermesSessionBackend(db=db)
        session_id = backend.create(
            "fleet_alpha_w1_deadbeef", model="test-model", fleet_id="alpha", worker_id="w-01",
        )
        row = db.get_session(session_id)
        assert row is not None
        assert row["source"] == "fleet"
        assert row["display_name"] == "fleet:alpha:w-01"
        backend.end(session_id, "fleet_drain")
        ended = db.get_session(session_id)
        assert ended["end_reason"] == "fleet_drain"
        assert ended["ended_at"] is not None
    finally:
        db.close()
