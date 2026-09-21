"""clawhub-run skill: prior install required; skill text untrusted."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "clawhub-run"
RUN_PY = SKILL_DIR / "scripts" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("clawhub_run_run", RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_skill_names_native_tools_and_prior_install():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`terminal`" in text
    assert "`delegate_task`" in text
    assert "untrusted" in text.lower()
    assert "same turn" in text.lower() or "earlier turn" in text.lower()
    assert RUN_PY.is_file()


def test_run_py_refuses_install_tool_in_same_env(monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("FLEET_TOOLS", "clawhub:clawhub-install,clawhub:clawhub-run")
    monkeypatch.setenv("FLEET_INSTRUCTION", "run foo")
    rc = module.main([])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
