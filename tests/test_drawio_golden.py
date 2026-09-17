"""Golden digests for the agatha drawio views.

``drawio_golden.json`` was recorded from the current exporter output on
2026-09-17, before the _outside group removal (commit 5) and the package split
(commit 6).  The digest is a SHA-256 of the XML string.  Any change to the XML
for a view must be explained in the commit message and the fixture re-recorded.

Commit 5 re-records the C2 and C3 digests (externals shift by a few pixels when
the virtual group is dropped); C1 must not change.  Commit 6 must leave all
three digests byte-identical.
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
    """C3 has an external (almacen, reached by servicio); digest re-recorded
    after commit 5 drops the virtual _outside group."""
    model = load((FIX / "agatha.json").read_text("utf-8"))
    views = to_views(model)
    c3 = next(v for v in views if v.level == "C3")
    assert _digest(c3.xml) == GOLD["C3:core"]["xml_sha256"]
