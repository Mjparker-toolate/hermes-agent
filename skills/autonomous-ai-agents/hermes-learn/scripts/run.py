#!/usr/bin/env python3
"""Append a lesson for n8n/fleet turns. In-agent use the `memory` tool instead.

Does not rewrite MEMORY.md (that would break prompt caching mid-session).
Writes JSONL under $HERMES_HOME/memories/fleet-lessons.jsonl.
Never reads secrets from argv.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

INSTRUCTION_MAX = 10000


def _hermes_home() -> Path:
    env = (os.environ.get("HERMES_HOME") or "").strip()
    if env:
        return Path(env)
    return Path.home() / ".hermes"


def main(argv: list[str] | None = None) -> int:
    del argv
    text = (os.environ.get("FLEET_INSTRUCTION") or "").strip()
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        print("error: missing FLEET_INSTRUCTION (or stdin)", file=sys.stderr)
        return 2
    if len(text) > INSTRUCTION_MAX:
        print("error: instruction exceeds 10000 characters", file=sys.stderr)
        return 2
    dest_dir = _hermes_home() / "memories"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "fleet-lessons.jsonl"
    record = {
        "ts": time.time(),
        "nodeId": os.environ.get("FLEET_NODE_ID") or "",
        "agentId": os.environ.get("FLEET_AGENT_ID") or "",
        "lesson": text,
    }
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    json.dump({"status": "ok", "output": str(dest), "error": None}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
