"""ClawHub-publishable hermes-fleet skill: example document + local client contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from hermes_cli.fleet_schema import V1_MAX_CONCURRENCY, load_fleet_document

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "hermes-fleet"
SKILL_MD = SKILL_DIR / "SKILL.md"
EXAMPLE = SKILL_DIR / "templates" / "fleet.example.yaml"
CLIENT = SKILL_DIR / "scripts" / "fleet_client.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("hermes_fleet_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_yaml_is_a_valid_v1_fleet_document():
    text = EXAMPLE.read_text(encoding="utf-8")
    config = load_fleet_document(text, source=str(EXAMPLE))
    assert config["fleet_id"]
    assert config["max_concurrency"] <= V1_MAX_CONCURRENCY
    assert config["replicas"] <= config["max_concurrency"]
    assert all(name.isupper() or "_" in name for name in config["secrets_ref"])
    assert not any("=" in name for name in config["secrets_ref"])
    assert "sk-" not in text
    assert "api_key:" not in text.lower() or "OPENROUTER_API_KEY" in text


def test_skill_points_agents_at_native_tools_and_the_http_surface():
    text = SKILL_MD.read_text(encoding="utf-8")
    for tool in ("`terminal`", "`read_file`", "`delegate_task`"):
        assert tool in text, f"skill must name native tool {tool}"
    for route in (
        "POST /fleet/start",
        "GET /fleet/{id}",
        "POST /fleet/{id}/scale",
        "POST /fleet/{id}/stop",
    ):
        assert route in text
    assert "127.0.0.1" in text
    assert "secrets_ref" in text
    assert "kill_switch" in text
    relative = "templates/fleet.example.yaml"
    assert relative in text
    assert (SKILL_DIR / relative).is_file()
    assert "scripts/fleet_client.py" in text
    assert CLIENT.is_file()


def test_client_refuses_to_run_without_a_token(monkeypatch, capsys):
    client = _load_client()
    monkeypatch.delenv("FLEET_HTTP_TOKEN", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path(client._hermes_home())))
    token_path = Path(client._hermes_home()) / "fleets" / ".http_token"
    if token_path.exists():
        token_path.unlink()
    rc = client.main(["status", "--fleet-id", "local-dev"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "FLEET_HTTP_TOKEN" in err
    assert "sk-" not in err


def test_client_prefers_hermes_home_over_hardcoded_dot_hermes(tmp_path, monkeypatch):
    client = _load_client()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert client._hermes_home() == tmp_path


def test_client_http_lifecycle_against_loopback_server(tmp_path, monkeypatch, capsys):
    from hermes_cli.fleet_http import start_background_server
    from hermes_cli.fleet_manager import FleetManager, MemorySessionBackend

    class _Noop:
        def launch(self, worker, template):
            return None

        def cancel(self, handle_dict) -> None:
            return None

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    token = "skill-client-token"
    monkeypatch.setenv("FLEET_HTTP_TOKEN", token)
    manager = FleetManager(sessions=MemorySessionBackend(), spawner=_Noop())
    server, thread, base, _resolved = start_background_server(
        host="127.0.0.1", port=0, manager=manager, token=token,
    )
    client = _load_client()
    try:
        rc = client.main([
            "--base-url", base, "start", "--config", str(EXAMPLE),
        ])
        assert rc == 0
        started = __import__("json").loads(capsys.readouterr().out)
        assert started["live_workers"] >= 1
        fleet_id = started["fleet_id"]

        rc = client.main(["--base-url", base, "status", "--fleet-id", fleet_id])
        assert rc == 0

        rc = client.main([
            "--base-url", base, "scale", "--fleet-id", fleet_id, "--replicas", "2",
        ])
        assert rc == 0
        scaled = __import__("json").loads(capsys.readouterr().out)
        assert scaled["live_workers"] == 2

        rc = client.main(["--base-url", base, "stop", "--fleet-id", fleet_id])
        assert rc == 0
        stopped = __import__("json").loads(capsys.readouterr().out)
        assert stopped["status"] == "stopped"
        assert stopped["live_workers"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
