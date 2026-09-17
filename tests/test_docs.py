"""Gate: the canonical form sentence is stated verbatim in the docs.

Any documentation that describes the authoring surface or interchange form
must quote CANONICAL_FORM verbatim — that is the single gate that prevents
the three half-statements in the original audit from drifting again.
"""

from __future__ import annotations

from pathlib import Path

from arb_mcp.domain.loading import CANONICAL_FORM

ROOT = Path(__file__).parent.parent


def test_canonical_form_is_stated_verbatim_in_readme_and_tools_md() -> None:
    """README.md and docs/TOOLS.md both contain the canonical form sentence."""
    for path in (ROOT / "README.md", ROOT / "docs" / "TOOLS.md"):
        text = path.read_text("utf-8")
        assert CANONICAL_FORM in text, (
            f"{path.relative_to(ROOT)} does not contain the canonical form sentence.\n"
            f"Expected:\n  {CANONICAL_FORM}"
        )
