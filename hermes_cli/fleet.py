"""``hermes fleet`` — start, inspect, scale, stop, and locally serve a worker fleet."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from hermes_cli.fleet_http import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    serve_forever,
    token_file_display,
)
from hermes_cli.fleet_manager import FleetError, FleetManager, default_manager
from hermes_cli.fleet_schema import FleetConfigError, load_fleet_document
from hermes_constants import display_hermes_home


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _load_config_arg(args: Namespace) -> dict:
    path = getattr(args, "config", None)
    if path:
        text = Path(path).read_text(encoding="utf-8")
        return load_fleet_document(text, source=str(path))
    raw = getattr(args, "json", None)
    if raw:
        return load_fleet_document(raw, source="--json")
    raise FleetConfigError("Provide --config PATH or --json OBJECT.")


def _manager() -> FleetManager:
    return default_manager()


def fleet_command(args: Namespace) -> int:
    """Entry point for ``hermes fleet``."""
    action = getattr(args, "fleet_action", None)
    handlers = {
        "start": _cmd_start,
        "status": _cmd_status,
        "scale": _cmd_scale,
        "stop": _cmd_stop,
        "delegate": _cmd_delegate,
        "list": _cmd_list,
        "ls": _cmd_list,
        "serve": _cmd_serve,
    }
    handler = handlers.get(action)
    if handler is None:
        print("Usage: hermes fleet {start|status|scale|stop|delegate|list|serve}")
        print("Run 'hermes fleet --help' for details.")
        return 1
    try:
        return handler(args)
    except FleetConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FleetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_start(args: Namespace) -> int:
    config = _load_config_arg(args)
    replicas = getattr(args, "replicas", None)
    if replicas is not None:
        config["replicas"] = replicas
        # Re-validate cap after CLI override.
        from hermes_cli.fleet_schema import normalize_fleet_config
        config = normalize_fleet_config(config)
    _print_json(_manager().start(config))
    return 0


def _cmd_status(args: Namespace) -> int:
    _print_json(_manager().get(args.fleet_id))
    return 0


def _cmd_scale(args: Namespace) -> int:
    _print_json(_manager().scale(args.fleet_id, replicas=args.replicas))
    return 0


def _cmd_stop(args: Namespace) -> int:
    _print_json(_manager().stop(args.fleet_id))
    return 0


def _cmd_delegate(args: Namespace) -> int:
    instruction = getattr(args, "instruction", None) or ""
    if not instruction.strip() and not sys.stdin.isatty():
        instruction = sys.stdin.read()
    tools_raw = getattr(args, "tools", None) or ""
    tools = [part.strip() for part in tools_raw.split(",") if part.strip()]
    _print_json(_manager().delegate(args.fleet_id, {
        "instruction": instruction,
        "agent_id": getattr(args, "agent_id", None) or "",
        "node_id": getattr(args, "node_id", None) or "",
        "kind": getattr(args, "kind", None) or "",
        "tools": tools,
    }))
    return 0


def _cmd_list(args: Namespace) -> int:
    _print_json(_manager().list())
    return 0


def _cmd_serve(args: Namespace) -> int:
    host = getattr(args, "host", None) or DEFAULT_HOST
    port = int(getattr(args, "port", None) or DEFAULT_PORT)

    def _ready(bound_host: str, bound_port: int) -> None:
        print(f"Hermes fleet HTTP listening on http://{bound_host}:{bound_port}")
        print("Routes: POST /fleet/start  GET /fleet/{{id}}  POST /fleet/{{id}}/scale  POST /fleet/{{id}}/stop  POST /fleet/{{id}}/delegate")
        print(f"Auth:   Authorization: Bearer <token>  (token file: {token_file_display()})")
        print("Bind is loopback-only in v1. State: " + f"{display_hermes_home()}/fleets/")
        sys.stdout.flush()

    try:
        serve_forever(host=host, port=port, ready=_ready)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
