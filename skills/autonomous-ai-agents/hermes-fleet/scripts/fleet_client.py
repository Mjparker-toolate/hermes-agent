#!/usr/bin/env python3
"""Call the loopback Hermes fleet HTTP API.

Reads FLEET_HTTP_TOKEN from the environment, or the token file under
HERMES_HOME/fleets/.http_token. Never prints the token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:8755"


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


def _request(method: str, url: str, payload: dict | None, token: str) -> tuple[int, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=headers)
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
    parser = argparse.ArgumentParser(description="Hermes fleet HTTP client")
    parser.add_argument("--base-url", default=os.environ.get("FLEET_HTTP_BASE", DEFAULT_BASE))
    sub = parser.add_subparsers(dest="action", required=True)

    start = sub.add_parser("start")
    start.add_argument("--config", required=True, help="Fleet YAML/JSON path")

    status = sub.add_parser("status")
    status.add_argument("--fleet-id", required=True)

    scale = sub.add_parser("scale")
    scale.add_argument("--fleet-id", required=True)
    scale.add_argument("--replicas", type=int, required=True)

    stop = sub.add_parser("stop")
    stop.add_argument("--fleet-id", required=True)

    args = parser.parse_args(argv)
    token = _token()
    if not token:
        print("error: missing FLEET_HTTP_TOKEN (or fleets/.http_token)", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    if args.action == "start":
        text = Path(args.config).read_text(encoding="utf-8")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            import yaml
            payload = yaml.safe_load(text)
        status_code, result = _request("POST", f"{base}/fleet/start", payload, token)
    elif args.action == "status":
        status_code, result = _request("GET", f"{base}/fleet/{args.fleet_id}", None, token)
    elif args.action == "scale":
        status_code, result = _request(
            "POST", f"{base}/fleet/{args.fleet_id}/scale",
            {"replicas": args.replicas}, token,
        )
    else:
        status_code, result = _request("POST", f"{base}/fleet/{args.fleet_id}/stop", {}, token)

    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except URLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
