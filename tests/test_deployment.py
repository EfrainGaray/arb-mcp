"""Deployment view: arbitrary-depth nesting, no dangling endpoints."""
from xml.etree import ElementTree as ET

from arb_mcp.application.convert_model import drawio_views
from arb_mcp.domain.loading import load

DEP = load(open("tests/fixtures/despliegue.json").read())


def _vids(xml):
    r = ET.fromstring(xml)
    return {o.get("id") for o in r.iter("object")} | {
        c.get("id") for c in r.iter("mxCell") if c.get("vertex") == "1" and c.get("id")}


def test_deployment_is_a_single_flat_view_labelled_deployment():
    views = drawio_views(DEP)
    assert len(views) == 1
    assert views[0]["level"] == "Deployment"


def test_deployment_nests_to_full_depth():
    """aws > region > ecs > api — four levels; the leaf must be present."""
    xml = drawio_views(DEP)[0]["xml"]
    ids = _vids(xml)
    for i in ("aws", "region", "ecs", "api", "db", "alb", "rds"):
        assert i in ids
    # api nested under ecs (parent chain intact)
    root = ET.fromstring(xml)
    api = next(c for c in root.iter("mxCell") if c.get("id") == "api")
    assert api.get("parent") == "ecs"


def test_deployment_edges_are_not_dangling():
    xml = drawio_views(DEP)[0]["xml"]
    ids = _vids(xml)
    edges = [c for c in ET.fromstring(xml).iter("mxCell") if c.get("edge") == "1"]
    assert len(edges) == 2
    for e in edges:
        assert e.get("source") in ids and e.get("target") in ids
