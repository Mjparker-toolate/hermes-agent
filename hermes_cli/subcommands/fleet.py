"""``hermes fleet`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_fleet_parser(subparsers, *, cmd_fleet: Callable) -> None:
    """Attach the ``fleet`` subcommand to ``subparsers``."""
    parser = subparsers.add_parser(
        "fleet",
        help="Local Hermes worker-fleet orchestration (n8n / ClawHub glue)",
        description=(
            "Start, scale, and stop a capped fleet of Hermes worker sessions. "
            "v1 binds loopback HTTP for n8n and stores fleet state under $HERMES_HOME/fleets/."
        ),
    )
    fleet_sub = parser.add_subparsers(dest="fleet_action")

    start = fleet_sub.add_parser("start", help="Create a fleet and spawn worker sessions")
    start.add_argument("--config", help="Path to a fleet YAML/JSON document")
    start.add_argument("--json", dest="json", help="Inline fleet JSON object")
    start.add_argument("--replicas", type=int, help="Live worker count (capped by max_concurrency, v1 max 5)")

    status = fleet_sub.add_parser("status", help="Show fleet status and workers")
    status.add_argument("fleet_id", help="Fleet id")

    scale = fleet_sub.add_parser("scale", help="Set live worker count (drain extras)")
    scale.add_argument("fleet_id", help="Fleet id")
    scale.add_argument("--replicas", type=int, required=True, help="Desired live workers")

    stop = fleet_sub.add_parser("stop", help="Drain and stop every worker in a fleet")
    stop.add_argument("fleet_id", help="Fleet id")

    fleet_sub.add_parser("list", aliases=["ls"], help="List known fleets")

    serve = fleet_sub.add_parser(
        "serve",
        help="Serve the loopback fleet HTTP API",
        description="Bind 127.0.0.1 and expose POST /fleet/start, GET /fleet/{id}, POST /fleet/{id}/scale, POST /fleet/{id}/stop.",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (loopback only in v1)")
    serve.add_argument("--port", type=int, default=8755, help="Bind port (default 8755)")

    parser.set_defaults(func=cmd_fleet)
