"""Regressions for Fable's integral audit (A1–A4). Each fails before its fix."""
from xml.etree import ElementTree as ET

from arb_mcp.application.convert_model import convert_model, drawio_views
from arb_mcp.domain.loading import load

C4_SPEC = {"nodeTypes": {"person": {"contains": []},
                         "softwareSystem": {"contains": ["container"]},
                         "container": {"contains": ["component"]},
                         "component": {"contains": []},
                         "decision": {"contains": [], "requires": ["status"]}},
           "relationTypes": {"uses": {}, "affects": {"from": ["decision"]}}}


def _m(nodes, relations):
    return {"version": "1.0", "name": "t", "scope": "system", "spec": C4_SPEC,
            "nodes": nodes, "relations": relations}


def _edges(xml):
    return [c for c in ET.fromstring(xml).iter("mxCell") if c.get("edge") == "1"]


def _vids(xml):
    r = ET.fromstring(xml)
    return {o.get("id") for o in r.iter("object")} | {
        c.get("id") for c in r.iter("mxCell") if c.get("vertex") == "1" and c.get("id")}


# A1: a relation to the focus system must survive in C2, source drawn
def test_a1_relation_to_focus_system_survives_in_c2():
    m = _m([{"id": "user", "type": "person", "name": "U"},
            {"id": "sys", "type": "softwareSystem", "name": "S",
             "nodes": [{"id": "web", "type": "container", "name": "W", "technology": "x"}]}],
           [{"from": "user", "to": "sys", "type": "uses"}])
    c2 = next(v for v in drawio_views(m) if v["level"] == "C2")
    assert len(_edges(c2["xml"])) >= 1  # relation must not vanish
    # every edge endpoint must be a drawn cell (no orphan/dangling)
    ids = _vids(c2["xml"]) | {"sys"}
    for e in _edges(c2["xml"]):
        assert e.get("source") in ids and e.get("target") in ids


# A2: flat view with 3-level nesting must not emit dangling endpoints
def test_a2_flat_no_dangling_endpoints_deep_nesting():
    spec = {"nodeTypes": {"actor": {"contains": []}, "system": {"contains": ["package"]},
                          "package": {"contains": ["useCase"]}, "useCase": {"contains": []}},
            "relationTypes": {"association": {"from": ["actor"]}}}
    m = {"version": "1.0", "name": "t", "scope": "undefined", "spec": spec,
         "nodes": [{"id": "a", "type": "actor", "name": "A"},
                   {"id": "sys", "type": "system", "name": "Sys", "nodes": [
                       {"id": "pkg", "type": "package", "name": "P", "nodes": [
                           {"id": "uc", "type": "useCase", "name": "UC"}]}]}],
         "relations": [{"from": "a", "to": "uc", "type": "association"}]}
    xml = drawio_views(m)[0]["xml"]
    ids = _vids(xml)
    for e in _edges(xml):
        assert e.get("source") in ids and e.get("target") in ids  # no dangling


# A3: structurizr must not emit a relation to an undeclared (non-C4) endpoint
def test_a3_structurizr_skips_non_c4_endpoints():
    m = _m([{"id": "sys", "type": "softwareSystem", "name": "S", "docs": "d"},
            {"id": "adr1", "type": "decision", "name": "D", "status": "accepted"}],
           [{"from": "adr1", "to": "sys", "type": "affects"}])
    dsl = convert_model(m, "structurizr")
    assert "adr1 ->" not in dsl  # adr1 is never declared as an element
    load(dsl)  # must still parse


# A4: a newline in a description must not silently vanish on round-trip
def test_a4_structurizr_newline_preserved():
    m = _m([{"id": "sys", "type": "softwareSystem", "name": "S",
             "description": "line1\nline2"}], [])
    reloaded = load(convert_model(m, "structurizr"))
    desc = reloaded["nodes"][0].get("description")
    assert desc and "line1" in desc and "line2" in desc  # not None


# M4: C3 view produces a well-formed, endpoint-consistent diagram
def test_m4_c3_view_is_consistent():
    m = load(open("tests/fixtures/agatha.arch").read())
    c3s = [v for v in drawio_views(m) if v["level"] == "C3"]
    assert c3s
    for v in c3s:
        ids = _vids(v["xml"])
        for e in _edges(v["xml"]):
            assert e.get("source") in ids and e.get("target") in ids
