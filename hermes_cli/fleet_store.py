"""Durable JSON store for fleet records under ``$HERMES_HOME/fleets/``.

Mutations take a per-fleet exclusive file lock so a CLI process and the
HTTP server cannot load/spawn/save the same record concurrently and
exceed the advertised concurrency cap.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Iterator

from hermes_constants import get_hermes_home
from utils import atomic_json_write

_FLEETS_DIRNAME = "fleets"
_STORE_FILE_MODE = 0o600
_LOCK_FILE_MODE = 0o600


def fleets_dir() -> Path:
    path = get_hermes_home() / _FLEETS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def fleet_path(fleet_id: str) -> Path:
    return fleets_dir() / f"{fleet_id}.json"


def fleet_lock_path(fleet_id: str) -> Path:
    return fleets_dir() / f".{fleet_id}.lock"


def _flock(fh, *, lock: bool) -> None:
    """Exclusive whole-file lock/unlock (fcntl on POSIX, msvcrt on Windows)."""
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK if lock else msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX if lock else fcntl.LOCK_UN)


class FleetFileLock:
    """Cross-process exclusive lock for one fleet id."""

    def __init__(self, fleet_id: str) -> None:
        if not fleet_id:
            raise ValueError("fleet lock requires a fleet_id")
        self.fleet_id = fleet_id
        self.path = fleet_lock_path(fleet_id)
        self._fh = None

    def __enter__(self) -> "FleetFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        try:
            os.chmod(self.path, _LOCK_FILE_MODE)
        except OSError:
            pass
        try:
            _flock(self._fh, lock=True)
        except Exception as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(f"fleet file lock unavailable for {self.fleet_id!r}") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        fh, self._fh = self._fh, None
        if fh is not None:
            with suppress(Exception):
                _flock(fh, lock=False)
            fh.close()


@contextmanager
def fleet_lock(fleet_id: str) -> Iterator[None]:
    """Hold the per-fleet exclusive lock for a load/mutate/save transaction."""
    with FleetFileLock(fleet_id):
        yield


def load_fleet(fleet_id: str) -> dict[str, Any] | None:
    path = fleet_path(fleet_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_fleet(record: dict[str, Any]) -> None:
    fleet_id = str(record.get("fleet_id") or "")
    if not fleet_id:
        raise ValueError("fleet record missing fleet_id")
    atomic_json_write(fleet_path(fleet_id), record, mode=_STORE_FILE_MODE)


def list_fleet_ids() -> list[str]:
    ids = []
    for path in sorted(fleets_dir().glob("*.json")):
        if path.name.startswith("."):
            continue
        ids.append(path.stem)
    return ids


def delete_fleet(fleet_id: str) -> None:
    path = fleet_path(fleet_id)
    if path.exists():
        path.unlink()
