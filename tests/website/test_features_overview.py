"""The Features Overview is the in-repo catalog of shipped Hermes capabilities.

`llms.txt` is how an LLM learns the whole docs tree (see
`test_generate_llms_txt.py`). The overview is the human — and in-checkout —
start page for "what can Hermes do?". A feature doc the overview omits is
the same failure class as a page missing from the generated index: the
agent answers that the product cannot do a thing it already ships.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES = REPO_ROOT / "website" / "docs" / "user-guide" / "features"
OVERVIEW = FEATURES / "overview.md"

# Relative markdown links to a sibling page: (tools.md), (./tools.md), (tools.md#anchor).
_FEATURE_LINK_RE = re.compile(r"\((?:\./)?([a-z0-9-]+\.md)(?:#[^)]*)?\)")


def _feature_pages() -> set[str]:
    return {path.name for path in FEATURES.glob("*.md") if path.name != "overview.md"}


def test_overview_links_every_feature_page():
    """The regression: a new feature doc that never lands on the catalog."""
    pages = _feature_pages()
    assert len(pages) > 30, "features dir resolved wrong — this test proves nothing"

    linked = set(_FEATURE_LINK_RE.findall(OVERVIEW.read_text(encoding="utf-8")))
    missing = sorted(pages - linked)
    assert not missing, (
        f"{len(missing)} feature pages missing from the Features Overview: "
        f"{missing} — add a one-line entry so the catalog absorbs the capability"
    )


def test_overview_does_not_invent_feature_pages():
    """A renamed page must not leave a dangling catalog link."""
    pages = _feature_pages()
    linked = set(_FEATURE_LINK_RE.findall(OVERVIEW.read_text(encoding="utf-8")))
    dangling = sorted(linked - pages)
    assert not dangling, (
        f"Features Overview links {dangling}, which are not in the features dir"
    )
