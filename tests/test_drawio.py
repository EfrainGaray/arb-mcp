"""drawio export: the XML parses, and carries the real C4 stencil styles."""
from pathlib import Path
from xml.etree import ElementTree as ET

from arb_mcp.application.convert_model import convert_source
from arb_mcp.domain.loading import load

FIX = Path(__file__).parent / "fixtures"
DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_drawio_is_well_formed_xml():
    xml = convert_source(DSL, "drawio")
    root = ET.fromstring(xml)  # raises on malformed XML
    assert root.tag == "mxfile"


def test_drawio_uses_real_c4_styles():
    xml = convert_source(DSL, "drawio")
    # person shape and the per-level fills, verbatim from the drawio stencil
    assert "shape=mxgraph.c4.person2" in xml
    assert "fillColor=#1061B0" in xml  # softwareSystem
    assert "fillColor=#23A2D9" in xml  # container
    assert "endArrow=blockThin" in xml  # the C4 relationship edge


def test_every_node_and_relation_becomes_a_cell():
    model = load(DSL)
    xml = convert_source(DSL, "drawio")
    root = ET.fromstring(xml)
    vertices = [c for c in root.iter("mxCell") if c.get("vertex") == "1"]
    edges = [c for c in root.iter("mxCell") if c.get("edge") == "1"]
    # simple.dsl: user, sys, web = 3 nodes; 1 relation
    assert len(vertices) == 3
    assert len(edges) == 1


def test_unknown_format_is_a_value_error():
    import pytest
    with pytest.raises(ValueError, match="unknown format"):
        convert_source(DSL, "png")
