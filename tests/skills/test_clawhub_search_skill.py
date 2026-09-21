"""clawhub-search skill: registry lookup stub; untrusted skill text."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "autonomous-ai-agents" / "clawhub-search"


def test_search_skill_does_not_eval_skill_text():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`web_search`" in text
    assert "`web_extract`" in text
    assert "untrusted" in text.lower()
    assert "never run" in text.lower() or "do not execute" in text.lower() or "do not eval" in text.lower()
    assert (SKILL_DIR / "scripts" / "run.py").is_file()
