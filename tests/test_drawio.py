"""drawio export: separate C4 views, each standalone XML with real stencil styles."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from arb_mcp.application.convert_model import convert_source, drawio_views
from arb_mcp.domain.loading import load


def _vertex_ids(root):
    """Vertex ids live on the <object> for C4 cards, on the <mxCell> for boundaries."""
    ids = {o.get("id") for o in root.iter("object")}
    ids |= {c.get("id") for c in root.iter("mxCell")
            if c.get("vertex") == "1" and c.get("id")}
    return ids

FIX = Path(__file__).parent / "fixtures"
DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_each_view_is_its_own_standalone_mxfile():
    views = json.loads(convert_source(DSL, "drawio"))["views"]
    assert views, "at least a C1 view"
    for v in views:
        root = ET.fromstring(v["xml"])
        assert root.tag == "mxfile"
        # exactly one diagram per file — never tabs
        assert len(root.findall("diagram")) == 1


def test_levels_are_separated_c1_c2_c3():
    """simple.dsl: a system with one container -> C1 and C2, no C3."""
    views = drawio_views(load(DSL))
    levels = [v["level"] for v in views]
    assert "C1" in levels
    assert "C2" in levels  # System has a container
    assert levels.count("C1") == 1  # one context view, always


def test_c1_does_not_expand_containers():
    """The context view shows systems as boxes, never their internals."""
    views = drawio_views(load(DSL))
    c1 = next(v for v in views if v["level"] == "C1")
    ids = _vertex_ids(ET.fromstring(c1["xml"]))
    assert "web" not in ids  # the container must not appear in C1
    assert "sys" in ids and "user" in ids


def test_c2_nests_containers_in_the_system_boundary():
    views = drawio_views(load(DSL))
    c2 = next(v for v in views if v["level"] == "C2")
    root = ET.fromstring(c2["xml"])
    web = next(o for o in root.iter("object") if o.get("id") == "web")
    inner = web.find("mxCell")
    assert inner.get("parent") == "sys"  # container nested inside the system boundary


def test_views_use_real_c4_styles():
    xml = "".join(v["xml"] for v in drawio_views(load(DSL)))
    assert "shape=mxgraph.c4.person2" in xml
    assert "fillColor=#23A2D9" in xml  # container level
    assert "endArrow=blockThin" in xml  # C4 relationship edge


def test_unknown_format_is_a_value_error():
    with pytest.raises(ValueError, match="unknown format"):
        convert_source(DSL, "png")
