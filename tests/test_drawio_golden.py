"""Golden digests for the agatha drawio views.

These tests are a **refactoring safety net**, not a behavioral contract.
They catch accidental pixel-level XML regressions that no higher-level assertion
(connectivity, nesting, style presence) would catch.  A digest change means the
XML changed; it does not mean behavior changed.

``drawio_golden.json`` was recorded from the exporter output on 2026-09-17.
The digest is a SHA-256 of the XML string.  Any change must be explained in the
commit message that re-records the fixture.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from arb_mcp.domain.drawio import to_views
from arb_mcp.domain.loading import load

FIX = Path(__file__).parent / "fixtures"
GOLD: dict[str, dict[str, str]] = json.loads((FIX / "drawio_golden.json").read_text("utf-8"))


def _digest(xml: str) -> str:
    return hashlib.sha256(xml.encode()).hexdigest()


def test_agatha_c1_digest_matches_golden() -> None:
    """C1 has no externals and no virtual group; its digest must never change."""
    model = load((FIX / "agatha.json").read_text("utf-8"))
    views = to_views(model)
    c1 = next(v for v in views if v.level == "C1")
    assert _digest(c1.xml) == GOLD["C1:system-landscape"]["xml_sha256"]


def test_agatha_c2_digest_matches_golden() -> None:
    """C2 has externals (usuario, correo, youtube); digest re-recorded after
    commit 5 drops the virtual _outside group."""
    model = load((FIX / "agatha.json").read_text("utf-8"))
    views = to_views(model)
    c2 = next(v for v in views if v.level == "C2")
    assert _digest(c2.xml) == GOLD["C2:agatha"]["xml_sha256"]


def test_agatha_c3_digest_matches_golden() -> None:
    """C3 externals are only what an edge reaching core touches (api, cli,
    almacen, youtube); digest re-recorded
    after commit 5 drops the virtual _outside group."""
    model = load((FIX / "agatha.json").read_text("utf-8"))
    views = to_views(model)
    c3 = next(v for v in views if v.level == "C3")
    assert _digest(c3.xml) == GOLD["C3:core"]["xml_sha256"]
