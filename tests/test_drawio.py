"""drawio export: separate C4 views, each standalone XML with real stencil styles."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from arb_mcp.application.convert_model import convert_source, drawio_views
from arb_mcp.domain.loading import load


def _vertex_ids(root: ET.Element) -> set[str | None]:
    """Vertex ids live on the <object> for C4 cards, on the <mxCell> for boundaries."""
    ids = {o.get("id") for o in root.iter("object")}
    ids |= {c.get("id") for c in root.iter("mxCell") if c.get("vertex") == "1" and c.get("id")}
    return ids


FIX = Path(__file__).parent / "fixtures"
DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_each_view_is_its_own_standalone_mxfile() -> None:
    views = json.loads(convert_source(DSL, "drawio"))["views"]
    assert views, "at least a C1 view"
    for v in views:
        root = ET.fromstring(v["xml"])
        assert root.tag == "mxfile"
        # exactly one diagram per file — never tabs
        assert len(root.findall("diagram")) == 1


def test_levels_are_separated_c1_c2_c3() -> None:
    """simple.dsl: a system with one container -> C1 and C2, no C3."""
    views = drawio_views(load(DSL))
    levels = [v["level"] for v in views]
    assert "C1" in levels
    assert "C2" in levels  # System has a container
    assert levels.count("C1") == 1  # one context view, always


def test_c1_does_not_expand_containers() -> None:
    """The context view shows systems as boxes, never their internals."""
    views = drawio_views(load(DSL))
    c1 = next(v for v in views if v["level"] == "C1")
    ids = _vertex_ids(ET.fromstring(c1["xml"]))
    assert "web" not in ids  # the container must not appear in C1
    assert "sys" in ids and "user" in ids


def test_c2_nests_containers_in_the_system_boundary() -> None:
    views = drawio_views(load(DSL))
    c2 = next(v for v in views if v["level"] == "C2")
    root = ET.fromstring(c2["xml"])
    web = next(o for o in root.iter("object") if o.get("id") == "web")
    inner = web.find("mxCell")
    assert inner is not None
    assert inner.get("parent") == "sys"  # container nested inside the system boundary


def test_views_use_real_c4_styles() -> None:
    xml = "".join(v["xml"] for v in drawio_views(load(DSL)))
    assert "shape=mxgraph.c4.person2" in xml
    assert "fillColor=#23A2D9" in xml  # container level
    assert "endArrow=blockThin" in xml  # C4 relationship edge


def test_unknown_format_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="unknown format"):
        convert_source(DSL, "png")


def _geom(elem: ET.Element) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) of the mxGeometry inside an object or mxCell."""
    g = elem.find(".//mxGeometry")
    assert g is not None
    return (
        int(g.get("x", "0")),
        int(g.get("y", "0")),
        int(g.get("width", "0")),
        int(g.get("height", "0")),
    )


def test_c2_externals_without_layout_form_a_column_below_the_boundary_and_never_overlap() -> None:
    """Refactoring safety net for external element placement.

    Asserts ordering and non-overlap (the invariant), not exact pixel values, so
    it survives layout shifts from internal refactors.  This is not a contract on
    coordinates; a digest test (test_drawio_golden.py) guards exact bytes."""
    views = drawio_views(load((FIX / "agatha.json").read_text("utf-8")))
    c2 = next(v for v in views if v["level"] == "C2")
    root = ET.fromstring(c2["xml"])

    # Boundary: the mxCell whose id is the system id and whose parent is "1".
    boundary = next(
        c
        for c in root.iter("mxCell")
        if c.get("vertex") == "1" and c.get("parent") == "1" and c.get("id") not in ("0", "1", None)
    )
    _bx, by, _bw, bh = _geom(boundary)
    boundary_bottom = by + bh

    # Externals: object nodes with parent "1" (not nested inside the boundary).
    externals = [
        obj
        for obj in root.iter("object")
        if obj.find("mxCell") is not None and obj.find("mxCell").get("parent") == "1"  # type: ignore[union-attr]
    ]
    assert externals, "agatha C2 must have externals (usuario, youtube, correo)"

    # Every external must sit entirely below the boundary box.
    for ext in externals:
        _ex, ey, _ew, _eh = _geom(ext)
        assert ey >= boundary_bottom, (
            f"external {ext.get('id')!r} top y={ey} overlaps boundary bottom={boundary_bottom}"
        )

    # Externals must form a non-overlapping column (sort by y).
    sorted_ext = sorted(externals, key=lambda e: _geom(e)[1])
    for i in range(1, len(sorted_ext)):
        prev = sorted_ext[i - 1]
        curr = sorted_ext[i]
        _px, py, _pw, ph = _geom(prev)
        _cx, cy, _cw, _ch = _geom(curr)
        assert cy >= py + ph, (
            f"external {curr.get('id')!r} y={cy} overlaps {prev.get('id')!r} bottom={py + ph}"
        )
