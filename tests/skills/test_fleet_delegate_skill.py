"""fleet-delegate n8n entry: env+stdin, no argv secrets, POST /fleet/{id}/delegate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "fleet-delegate"
RUN_PY = SKILL_DIR / "scripts" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("fleet_delegate_run", RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_names_native_tools_and_delegate_route():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`terminal`" in text
    assert "`read_file`" in text
    assert "`delegate_task`" in text
    assert "POST /fleet/{id}/delegate" in text
    assert "FLEET_HTTP_TOKEN" in text
    assert RUN_PY.is_file()


def test_run_py_posts_delegate_and_ignores_argv_token(tmp_path, monkeypatch, capsys):
    from hermes_cli.fleet_http import start_background_server
    from hermes_cli.fleet_manager import FleetManager, MemorySessionBackend

    class _Noop:
        def launch(self, worker, template):
            return None

        def cancel(self, handle_dict) -> None:
            return None

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    token = "delegate-skill-token"
    monkeypatch.setenv("FLEET_HTTP_TOKEN", token)
    manager = FleetManager(sessions=MemorySessionBackend(), spawner=_Noop())
    server, thread, base, _resolved = start_background_server(
        host="127.0.0.1", port=0, manager=manager, token=token,
    )
    module = _load()
    try:
        manager.start({
            "fleet_id": "hermes-clawhub-combined",
            "max_concurrency": 2,
            "replicas": 1,
        })
        monkeypatch.setenv("FLEET_HTTP_BASE", base)
        monkeypatch.setenv("FLEET_ID", "hermes-clawhub-combined")
        monkeypatch.setenv("FLEET_INSTRUCTION", "search yaml")
        monkeypatch.setenv("FLEET_NODE_ID", "n1")
        monkeypatch.setenv("FLEET_AGENT_ID", "orchestrator")
        rc = module.main(["--token", "should-be-ignored"])
        assert rc == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "ok"
        assert payload["nodeId"] == "n1"
        assert token not in captured.err
        assert "should-be-ignored" not in captured.err
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_run_py_refuses_install_and_run_same_tools(monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("FLEET_TOOLS", "clawhub:clawhub-install,clawhub:clawhub-run")
    monkeypatch.setenv("FLEET_INSTRUCTION", "nope")
    rc = module.main([])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "same turn" in payload["error"]
