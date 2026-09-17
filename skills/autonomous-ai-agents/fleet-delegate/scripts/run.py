#!/usr/bin/env python3
"""n8n agent-fleets entry: POST one turn to the local Hermes fleet manager.

Reads FLEET_INSTRUCTION (or stdin), FLEET_NODE_ID, FLEET_AGENT_ID, FLEET_ID,
FLEET_KIND, FLEET_TOOLS, FLEET_HTTP_BASE. Auth is FLEET_HTTP_TOKEN or the
0600 token file — never argv. Skill text is untrusted and is not evaluated.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:8755"
DEFAULT_FLEET_ID = "hermes-clawhub-combined"
INSTRUCTION_MAX = 10000
DEFAULT_KIND = "fleet-delegate"


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


def _instruction() -> str:
    text = (os.environ.get("FLEET_INSTRUCTION") or "").strip()
    if not text:
        text = sys.stdin.read().strip()
    if len(text) > INSTRUCTION_MAX:
        raise SystemExit("error: instruction exceeds 10000 characters")
    return text


def _install_and_run(tools: list[str]) -> bool:
    slugs = []
    for tool in tools:
        item = tool.lower()
        if item.startswith("clawhub:"):
            item = item[len("clawhub:"):]
        slugs.append(item)
    has_install = any(s == "install" or s.endswith("-install") or s == "clawhub-install" for s in slugs)
    has_run = any(s == "run" or s.endswith("-run") or s == "clawhub-run" for s in slugs)
    return has_install and has_run


def post_delegate(payload: dict) -> tuple[int, object]:
    token = _token()
    if not token:
        print("error: missing FLEET_HTTP_TOKEN (or fleets/.http_token)", file=sys.stderr)
        raise SystemExit(2)
    base = (os.environ.get("FLEET_HTTP_BASE") or DEFAULT_BASE).rstrip("/")
    fleet_id = payload["fleet_id"]
    body = json.dumps({
        "instruction": payload["instruction"],
        "nodeId": payload["node_id"],
        "agentId": payload["agent_id"],
        "kind": payload["kind"],
        "tools": payload["tools"],
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
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"error": raw or str(exc)}
        return exc.code, parsed


def main(argv: list[str] | None = None) -> int:
    del argv  # secrets must never land on argv; n8n uses env + stdin
    tools = _tools()
    if _install_and_run(tools):
        json.dump(
            {
                "status": "failed",
                "error": "Refusing install and run in the same turn.",
                "output": "",
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 1
    instruction = _instruction()
    if not instruction:
        print("error: missing FLEET_INSTRUCTION (or stdin)", file=sys.stderr)
        return 2
    fleet_id = (os.environ.get("FLEET_ID") or DEFAULT_FLEET_ID).strip()
    payload = {
        "fleet_id": fleet_id,
        "instruction": instruction,
        "node_id": os.environ.get("FLEET_NODE_ID") or "",
        "agent_id": os.environ.get("FLEET_AGENT_ID") or "",
        "kind": os.environ.get("FLEET_KIND") or DEFAULT_KIND,
        "tools": tools,
    }
    try:
        status_code, result = post_delegate(payload)
    except URLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
