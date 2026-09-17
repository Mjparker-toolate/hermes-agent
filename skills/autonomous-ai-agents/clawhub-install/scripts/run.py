#!/usr/bin/env python3
"""n8n entry for clawhub:clawhub-install. Refuses to also run in this turn."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:8755"
DEFAULT_FLEET_ID = "hermes-clawhub-combined"
KIND = "clawhub-install"
INSTRUCTION_MAX = 10000


def _hermes_home() -> Path:
    env = (os.environ.get("HERMES_HOME") or "").strip()
    if env:
        return Path(env)
    return Path.home() / ".hermes"


def _token() -> str:
    env = (os.environ.get("FLEET_HTTP_TOKEN") or "").strip()
    if env:
        return env
    path = _hermes_home() / "fleets" / ".http_token"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _tools() -> list[str]:
    raw = os.environ.get("FLEET_TOOLS") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _has_run(tools: list[str]) -> bool:
    for tool in tools:
        item = tool.lower()
        if item.startswith("clawhub:"):
            item = item[len("clawhub:"):]
        if item in {"run", "clawhub-run"} or item.endswith("-run"):
            return True
    return False


def _instruction() -> str:
    text = (os.environ.get("FLEET_INSTRUCTION") or "").strip()
    if not text:
        text = sys.stdin.read().strip()
    if len(text) > INSTRUCTION_MAX:
        raise SystemExit("error: instruction exceeds 10000 characters")
    return text


def main(argv: list[str] | None = None) -> int:
    del argv
    tools = _tools()
    if _has_run(tools):
        json.dump({
            "status": "failed",
            "error": "Refusing install and run in the same turn.",
            "output": "",
        }, sys.stdout)
        sys.stdout.write("\n")
        return 1
    instruction = _instruction()
    if not instruction:
        print("error: missing FLEET_INSTRUCTION (or stdin)", file=sys.stderr)
        return 2
    token = _token()
    if not token:
        print("error: missing FLEET_HTTP_TOKEN (or fleets/.http_token)", file=sys.stderr)
        return 2
    fleet_id = (os.environ.get("FLEET_ID") or DEFAULT_FLEET_ID).strip()
    base = (os.environ.get("FLEET_HTTP_BASE") or DEFAULT_BASE).rstrip("/")
    body = json.dumps({
        "instruction": instruction,
        "nodeId": os.environ.get("FLEET_NODE_ID") or "",
        "agentId": os.environ.get("FLEET_AGENT_ID") or "",
        "kind": os.environ.get("FLEET_KIND") or KIND,
        "tools": tools or ["clawhub:clawhub-install"],
    }).encode("utf-8")
    request = Request(
        f"{base}/fleet/{fleet_id}/delegate",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            status_code = response.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"error": raw or str(exc)}
        status_code = exc.code
    except URLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(parsed, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
