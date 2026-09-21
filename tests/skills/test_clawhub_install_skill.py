"""clawhub-install skill: install never shares a turn with run."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "clawhub-install"
RUN_PY = SKILL_DIR / "scripts" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("clawhub_install_run", RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_skill_names_terminal_and_forbids_same_turn_run():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`terminal`" in text
    assert "`read_file`" in text
    assert "never run" in text.lower()
    assert RUN_PY.is_file()


def test_install_run_py_refuses_run_tool_in_same_env(monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("FLEET_TOOLS", "clawhub:clawhub-install,clawhub:clawhub-run")
    monkeypatch.setenv("FLEET_INSTRUCTION", "install foo")
    rc = module.main(["--api-key", "sk-not-used"])
    assert rc == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "failed"
    assert "sk-not-used" not in captured.err
