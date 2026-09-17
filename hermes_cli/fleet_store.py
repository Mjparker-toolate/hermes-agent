"""Durable JSON store for fleet records under ``$HERMES_HOME/fleets/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from utils import atomic_json_write

_FLEETS_DIRNAME = "fleets"
_STORE_FILE_MODE = 0o600


def fleets_dir() -> Path:
    path = get_hermes_home() / _FLEETS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def fleet_path(fleet_id: str) -> Path:
    return fleets_dir() / f"{fleet_id}.json"


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
