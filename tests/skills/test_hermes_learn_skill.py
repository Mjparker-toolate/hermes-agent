"""hermes-learn skill: agent uses `memory`; n8n appends JSONL, not MEMORY.md."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "hermes-learn"
RUN_PY = SKILL_DIR / "scripts" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("hermes_learn_run", RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_learn_skill_points_at_memory_tool():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`memory`" in text
    assert "`read_file`" in text
    assert "MEMORY.md" in text
    assert RUN_PY.is_file()


def test_learn_run_py_appends_jsonl_under_hermes_home(tmp_path, monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("FLEET_INSTRUCTION", "prefer loopback fleet HTTP")
    monkeypatch.setenv("FLEET_NODE_ID", "n-learn")
    rc = module.main(["--token", "nope"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    dest = tmp_path / "memories" / "fleet-lessons.jsonl"
    assert dest.is_file()
    line = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
    assert line["lesson"] == "prefer loopback fleet HTTP"
    assert line["nodeId"] == "n-learn"
    assert not (tmp_path / "memories" / "MEMORY.md").exists()
