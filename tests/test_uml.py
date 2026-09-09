"""The same canonical model, a different notation: UML use cases.

Proves agnosticism end to end — one schema serves C4 and UML — and that the
drawio exporter switches stencils by reading the spec, not a flag."""
from pathlib import Path
from xml.etree import ElementTree as ET

from arb_mcp.application.convert_model import convert_model, drawio_views
from arb_mcp.domain.loading import load

UML = (Path(__file__).parent / "fixtures" / "uml-casos-uso.json").read_text("utf-8")


def test_uml_validates_against_the_same_schema():
    m = load(UML)  # must survive the normative schema, unchanged
    assert m["spec"]["nodeTypes"].keys() >= {"actor", "system", "useCase"}


def test_uml_exports_to_dsl():
    dsl = convert_model(load(UML), "arch")
    assert dsl.startswith("model")
    assert 'actor "Cliente"' in dsl
    assert "-association->" in dsl and "-include->" in dsl


def test_uml_drawio_uses_uml_stencil_not_c4():
    views = drawio_views(load(UML))
    assert len(views) == 1 and views[0]["level"] == "UML"  # flat, no C1/C2/C3
    xml = views[0]["xml"]
    assert "shape=umlActor" in xml       # actors as stick figures
    assert "ellipse;" in xml             # use cases as ellipses
    assert "fillColor=#23A2D9" not in xml  # no C4 container blue here
    root = ET.fromstring(xml)
    assert len([c for c in root.iter("mxCell") if c.get("edge") == "1"]) == 5


def test_c4_model_still_gets_separate_views():
    """Guard: the dispatcher must not send a C4 model down the flat path."""
    c4 = (Path(__file__).parent / "fixtures" / "simple.dsl").read_text("utf-8")
    levels = [v["level"] for v in drawio_views(load(c4))]
    assert "C1" in levels and "UML" not in levels
