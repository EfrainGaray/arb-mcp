"""Regressions for Fable's second audit: referential integrity and cell ids."""
import json

from arb_mcp.application.build_model import build_model
from arb_mcp.application.convert_model import drawio_views
from arb_mcp.application.validate_model import validate_model


def _model(nodes, relations):
    return {"version": "1.0", "name": "t", "scope": "system",
            "spec": {"nodeTypes": {"person": {"contains": []},
                                   "softwareSystem": {"contains": ["container"]},
                                   "container": {"contains": []}},
                     "relationTypes": {"uses": {}}},
            "nodes": nodes, "relations": relations}


def test_dangling_relation_endpoint_blocks_and_never_crashes():
    m = _model(
        [{"id": "api", "type": "softwareSystem", "name": "API"}],
        [{"from": "api", "to": "ghost", "type": "uses"}],
    )
    report = validate_model(m)
    assert not report.may_merge
    assert any(f.rule == "model.relation.endpoint" for f in report.blocking)
    # and drawio must not raise on the dangling endpoint
    views = drawio_views(m)
    assert views  # C1 at least, no KeyError


def test_duplicate_id_is_blocked():
    m = _model(
        [{"id": "a", "type": "person", "name": "A"},
         {"id": "a", "type": "softwareSystem", "name": "A2"}],
        [],
    )
    report = validate_model(m)
    assert any(f.rule == "model.id.duplicate" for f in report.blocking)


def test_edge_cell_id_cannot_collide_with_a_node_id():
    """A node literally named 'e0' must not clash with the first edge's cell id."""
    m = _model(
        [{"id": "e0", "type": "person", "name": "Odd"},
         {"id": "sys", "type": "softwareSystem", "name": "Sys"}],
        [{"from": "e0", "to": "sys", "type": "uses"}],
    )
    from xml.etree import ElementTree as ET
    root = ET.fromstring(next(v for v in drawio_views(m) if v["level"] == "C1")["xml"])
    obj_ids = [o.get("id") for o in root.iter("object")]
    edge_ids = [c.get("id") for c in root.iter("mxCell") if c.get("edge") == "1"]
    assert obj_ids.count("e0") == 1        # the node lives on the <object>
    assert "e0" not in edge_ids            # the edge id is namespaced (:e0), no clash


def test_build_model_does_not_mutate_callers_relations():
    rels = [{"from": "a", "to": "b"}]
    build_model([{"id": "a", "type": "person", "name": "A"}], rels)
    assert "type" not in rels[0]  # caller's dict untouched


def test_excessive_nesting_is_a_model_error():
    """Fable B2: agent-generated deep nesting fails as ModelError, not RecursionError."""
    from arb_mcp.domain.loading import ModelError, load
    node = {"id": "n0", "type": "deploymentNode", "name": "n"}
    cur = node
    for i in range(1, 40):
        child = {"id": f"n{i}", "type": "deploymentNode", "name": "n"}
        cur["nodes"] = [child]; cur = child
    model = json.dumps({"version": "1.0", "name": "x", "scope": "deployment",
                        "spec": {"nodeTypes": {"deploymentNode": {"contains": ["deploymentNode"]}}},
                        "nodes": [node], "relations": []})
    import pytest
    with pytest.raises(ModelError, match="nesting"):
        load(model)
