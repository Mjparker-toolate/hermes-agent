"""Loopback fleet HTTP: auth, routes, concurrency envelope, bind guard."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from hermes_cli.fleet_http import (
    bind_fleet_server,
    post_loopback_callback,
    start_background_server,
)
from hermes_cli.fleet_manager import FleetManager, MemorySessionBackend
from hermes_cli.fleet_schema import FleetConfigError, is_loopback_host


class _NoopSpawner:
    def launch(self, worker, template):
        return None

    def cancel(self, handle_dict) -> None:
        return None


def _start(tmp_path, monkeypatch, token: str = "test-fleet-token"):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    manager = FleetManager(sessions=MemorySessionBackend(), spawner=_NoopSpawner())
    server, thread, base, resolved = start_background_server(
        host="127.0.0.1", port=0, manager=manager, token=token,
    )
    return server, thread, base, resolved, manager


def _stop(server, thread) -> None:
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def _call(base: str, method: str, path: str, token: str | None, body: dict | None = None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{base}{path}", data=payload, method=method, headers=headers)
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"error": raw or str(exc)}
        return exc.code, parsed


def test_health_does_not_require_auth(tmp_path, monkeypatch):
    server, thread, base, _token, _mgr = _start(tmp_path, monkeypatch)
    try:
        status, payload = _call(base, "GET", "/health", token=None)
        assert status == 200
        assert payload["ok"] is True
        assert payload["service"] == "hermes-fleet"
    finally:
        _stop(server, thread)


def test_mutating_routes_require_bearer_token(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        status, payload = _call(base, "POST", "/fleet/start", token=None, body={"fleet_id": "x"})
        assert status == 401
        assert payload["code"] == "unauthorized"
        status, payload = _call(
            base, "POST", "/fleet/start", token="wrong", body={"fleet_id": "x"},
        )
        assert status == 401
        assert payload["code"] == "unauthorized"
        assert token
    finally:
        _stop(server, thread)


def test_start_status_scale_stop_lifecycle(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        doc = {
            "fleet_id": "n8n-dev",
            "max_concurrency": 3,
            "replicas": 1,
            "secrets_ref": ["OPENROUTER_API_KEY"],
        }
        status, started = _call(base, "POST", "/fleet/start", token, doc)
        assert status == 201
        assert started["fleet_id"] == "n8n-dev"
        assert started["live_workers"] == 1
        assert started["status"] == "running"

        status, got = _call(base, "GET", "/fleet/n8n-dev", token)
        assert status == 200
        assert got["live_workers"] == 1

        status, scaled = _call(
            base, "POST", "/fleet/n8n-dev/scale", token, {"replicas": 3},
        )
        assert status == 200
        assert scaled["live_workers"] == 3
        assert scaled["replicas"] == 3

        status, stopped = _call(base, "POST", "/fleet/n8n-dev/stop", token, {})
        assert status == 200
        assert stopped["status"] == "stopped"
        assert stopped["live_workers"] == 0
    finally:
        _stop(server, thread)


def test_scale_over_cap_returns_409(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        _call(
            base, "POST", "/fleet/start", token,
            {"fleet_id": "capped", "max_concurrency": 2, "replicas": 1},
        )
        status, payload = _call(
            base, "POST", "/fleet/capped/scale", token, {"replicas": 5},
        )
        assert status == 409
        assert payload["code"] == "concurrency_cap"
        status, got = _call(base, "GET", "/fleet/capped", token)
        assert got["live_workers"] == 1
    finally:
        _stop(server, thread)


def test_kill_switch_start_is_403(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        status, payload = _call(
            base, "POST", "/fleet/start", token,
            {"fleet_id": "killed", "kill_switch": True, "replicas": 1},
        )
        assert status == 403
        assert payload["code"] == "kill_switch"
    finally:
        _stop(server, thread)


def test_non_loopback_bind_is_refused():
    with pytest.raises(Exception) as exc:
        bind_fleet_server(host="0.0.0.0", port=0, token="x", generate_token=False)
    err = exc.value
    assert getattr(err, "code", "") == "bind_not_loopback"
    assert not is_loopback_host("0.0.0.0")


def test_unknown_route_is_404(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        status, payload = _call(base, "POST", "/fleet/nope/explode", token, {})
        assert status == 404
        assert payload["code"] == "not_found"
    finally:
        _stop(server, thread)


def test_callback_refuses_non_loopback_and_posts_to_loopback():
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            received.append(json.loads(raw.decode("utf-8")))
            body = b'{"ok": true}\n'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        post_loopback_callback(
            f"http://{host}:{port}/hook",
            {"event": "started", "fleet": {"fleet_id": "cb"}},
        )
        assert received == [{"event": "started", "fleet": {"fleet_id": "cb"}}]
        post_loopback_callback("http://example.com/hook", {"event": "nope"})
        assert len(received) == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_invalid_json_body_is_400(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        request = Request(
            f"{base}/fleet/start",
            data=b"not-json",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with pytest.raises(URLError):
            try:
                with urlopen(request, timeout=5) as response:
                    response.read()
            except HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 400
                assert payload["code"] == "invalid_json"
                raise
    finally:
        _stop(server, thread)


def test_start_rejects_embedded_secret_in_http_body(tmp_path, monkeypatch):
    server, thread, base, token, _mgr = _start(tmp_path, monkeypatch)
    try:
        status, payload = _call(
            base, "POST", "/fleet/start", token,
            {"fleet_id": "leaky", "api_key": "sk-should-not-land"},
        )
        assert status == 400
        assert payload["code"] == "secrets_embedded"
    finally:
        _stop(server, thread)


def test_normalize_error_code_survives_http_envelope():
    """Keep the HTTP error table honest: schema codes are the wire codes."""
    with pytest.raises(FleetConfigError) as exc:
        from hermes_cli.fleet_schema import normalize_fleet_config
        normalize_fleet_config({"fleet_id": "x", "max_concurrency": 99})
    assert exc.value.code == "concurrency_cap"
