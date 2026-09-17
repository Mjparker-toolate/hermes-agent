"""Loopback-only HTTP surface for fleet start/status/scale/stop.

n8n (or a ClawHub-installed skill) calls this local server. v1 binds
127.0.0.1 / ::1 only and requires a bearer token stored under
``$HERMES_HOME/fleets/.http_token`` (or ``FLEET_HTTP_TOKEN``).
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from hermes_cli.fleet_manager import (
    FleetError,
    FleetManager,
    default_manager,
)
from hermes_cli.fleet_schema import FleetConfigError, is_loopback_host, is_loopback_url
from hermes_cli.fleet_store import fleets_dir
from hermes_constants import display_hermes_home

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8755
_MAX_BODY_BYTES = 64 * 1024
_TOKEN_FILE = ".http_token"
_TOKEN_MODE = 0o600
_CALLBACK_TIMEOUT_SECONDS = 5


class FleetHttpError(Exception):
    def __init__(self, status: int, message: str, *, code: str = "http_error") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def resolve_http_token(*, generate: bool = False) -> str:
    """Bearer token from env, then the 0600 token file, optionally generated."""
    env = (os.environ.get("FLEET_HTTP_TOKEN") or "").strip()
    if env:
        return env
    path = fleets_dir() / _TOKEN_FILE
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    if not generate:
        return ""
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, _TOKEN_MODE)
    return token


def token_file_display() -> str:
    return f"{display_hermes_home()}/fleets/{_TOKEN_FILE}"


def _json_bytes(payload: MappingLike) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


MappingLike = dict[str, Any]


def post_loopback_callback(url: str, payload: MappingLike) -> None:
    """Best-effort POST of a fleet event; refused unless the URL is loopback."""
    if not url or not is_loopback_url(url):
        return
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(request, timeout=_CALLBACK_TIMEOUT_SECONDS) as response:  # noqa: S310 — loopback-only
        response.read()


def _manager_with_callbacks() -> FleetManager:
    def _callback(payload: MappingLike) -> None:
        fleet = payload.get("fleet") or {}
        url = str(fleet.get("webhook_callback_url") or "")
        if not url:
            return
        try:
            post_loopback_callback(url, payload)
        except Exception:
            # Callbacks are best-effort; fleet state is already persisted.
            return

    return FleetManager(callback=_callback)


def _parse_path(path: str) -> tuple[str, str | None, str | None]:
    """Return (action, fleet_id, extra) for /fleet/... routes."""
    parsed = urlparse(path)
    parts = [part for part in parsed.path.split("/") if part]
    if parts == ["health"]:
        return "health", None, None
    if len(parts) < 1 or parts[0] != "fleet":
        return "unknown", None, None
    if len(parts) == 1:
        return "unknown", None, None
    if parts[1] == "start" and len(parts) == 2:
        return "start", None, None
    if len(parts) == 2:
        return "status", parts[1], None
    if len(parts) == 3 and parts[2] in {"scale", "stop"}:
        return parts[2], parts[1], None
    return "unknown", None, None


def make_handler(manager: FleetManager, token: str) -> type[BaseHTTPRequestHandler]:
    class FleetHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _check_auth(self) -> None:
            if not token:
                raise FleetHttpError(401, "Fleet HTTP token is not configured.", code="unauthorized")
            header = self.headers.get("Authorization") or ""
            prefix = "Bearer "
            if not header.startswith(prefix) or header[len(prefix):].strip() != token:
                raise FleetHttpError(401, "Invalid or missing bearer token.", code="unauthorized")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > _MAX_BODY_BYTES:
                raise FleetHttpError(413, "Request body too large.", code="body_too_large")
            raw = self.rfile.read(length) if length else b"{}"
            if not raw:
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FleetHttpError(400, f"Body must be JSON: {exc}", code="invalid_json") from exc
            if not isinstance(payload, dict):
                raise FleetHttpError(400, "JSON body must be an object.", code="invalid_json")
            return payload

        def _send(self, status: int, payload: MappingLike) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _send_error_payload(self, status: int, message: str, code: str) -> None:
            self._send(status, {"error": message, "code": code})

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            try:
                action, fleet_id, _extra = _parse_path(self.path)
                if action == "health":
                    self._send(200, {"ok": True, "service": "hermes-fleet"})
                    return
                self._check_auth()
                if action == "start" and method == "POST":
                    result = manager.start(self._read_json())
                    self._send(201, result)
                    return
                if action == "status" and method == "GET" and fleet_id:
                    self._send(200, manager.get(fleet_id))
                    return
                if action == "scale" and method == "POST" and fleet_id:
                    body = self._read_json()
                    replicas = body.get("replicas")
                    if isinstance(replicas, bool) or not isinstance(replicas, int):
                        raise FleetHttpError(400, "scale requires integer 'replicas'.", code="invalid_config")
                    self._send(200, manager.scale(fleet_id, replicas=replicas))
                    return
                if action == "stop" and method == "POST" and fleet_id:
                    self._send(200, manager.stop(fleet_id))
                    return
                raise FleetHttpError(404, f"No route for {method} {self.path}", code="not_found")
            except FleetConfigError as exc:
                self._send_error_payload(400, str(exc), getattr(exc, "code", "invalid_config"))
            except FleetError as exc:
                self._send_error_payload(exc.status, str(exc), exc.code)
            except FleetHttpError as exc:
                self._send_error_payload(exc.status, str(exc), exc.code)
            except ValueError as exc:
                self._send_error_payload(400, str(exc), "invalid_config")
            except Exception:
                self._send_error_payload(500, "Internal fleet error.", "internal")

    return FleetHandler


class LoopbackHTTPServer(ThreadingMixIn, ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def bind_fleet_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    manager: FleetManager | None = None,
    token: str | None = None,
    generate_token: bool = True,
) -> tuple[LoopbackHTTPServer, str]:
    if not is_loopback_host(host):
        raise FleetHttpError(
            400,
            f"v1 fleet HTTP refuses non-loopback bind {host!r}; use 127.0.0.1.",
            code="bind_not_loopback",
        )
    resolved = token if token is not None else resolve_http_token(generate=generate_token)
    if not resolved:
        raise FleetHttpError(401, "Set FLEET_HTTP_TOKEN or run with token generation.", code="unauthorized")
    handler = make_handler(manager or _manager_with_callbacks(), resolved)
    server = LoopbackHTTPServer((host, port), handler)
    return server, resolved


def serve_forever(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    manager: FleetManager | None = None,
    ready: Callable[[str, int], None] | None = None,
) -> None:
    server, _token = bind_fleet_server(host=host, port=port, manager=manager)
    bound_host, bound_port = server.server_address[:2]
    if ready:
        ready(str(bound_host), int(bound_port))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def start_background_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = 0,
    manager: FleetManager | None = None,
    token: str | None = None,
) -> tuple[LoopbackHTTPServer, threading.Thread, str, str]:
    """Start a daemon thread (tests / programmatic use). Port 0 picks a free port."""
    server, resolved = bind_fleet_server(
        host=host, port=port, manager=manager, token=token, generate_token=token is None,
    )
    thread = threading.Thread(target=server.serve_forever, name="hermes-fleet-http", daemon=True)
    thread.start()
    bound_host, bound_port = server.server_address[:2]
    base = f"http://{bound_host}:{bound_port}"
    return server, thread, base, resolved
