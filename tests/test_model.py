"""The typed model is a lossless mirror of the wire form, field by field."""

from __future__ import annotations

import json
from typing import Any

from arb_mcp.domain.loading import load
from arb_mcp.domain.model import Model

# Every optional field the schema knows, populated once.
SINK: dict[str, Any] = {
    "version": "1.0",
    "name": "Sink",
    "description": "everything at once",
    "scope": "system",
    "spec": {
        "extends": "https://example.test/c4.spec.json",
        "nodeTypes": {
            "thing": {"description": "a thing", "contains": ["part"], "requires": ["owner"]},
            "part": {"contains": []},
            "loose": {},
        },
        "relationTypes": {
            "uses": {},
            "peers": {
                "description": "symmetric",
                "from": ["thing"],
                "to": ["thing"],
                "directed": False,
            },
        },
    },
    "nodes": [
        {
            "id": "t1",
            "type": "thing",
            "name": "T1",
            "description": "d",
            "technology": "Go",
            "tags": ["core", "x"],
            "properties": {"owner": "team-a"},
            "docs": [
                {"title": "Overview", "content": "..."},
                {"title": "Runbook", "content": "...", "format": "asciidoc", "date": "2026-09-09"},
            ],
            "origin": {"tool": "scanner", "command": "scan --all", "date": "2026-09-09T00:00:00Z"},
            "nodes": [{"id": "p1", "type": "part", "name": "P1"}],
        },
        {"id": "t2", "type": "thing", "name": "T2", "properties": {"owner": "team-b"}},
        {"id": "l1", "type": "loose", "name": "L"},
    ],
    "relations": [
        {
            "id": "r1",
            "from": "t1",
            "to": "t2",
            "type": "peers",
            "description": "talk",
            "technology": "gRPC",
            "tags": ["sync"],
            "properties": {"sla": "99.9"},
            "origin": {"tool": "scanner"},
        },
        {"from": "p1", "to": "l1"},
    ],
    "views": [
        {
            "id": "all",
            "title": "All",
            "description": "everything",
            "include": ["*", {"type": "thing"}],
            "exclude": [{"tag": "x"}],
            "layout": {
                "direction": "right",
                "origin": "imported",
                "tool": "dagre@11.4.1",
                "modelDigest": "abc123",
                "placements": [
                    {"node": "t1", "rank": 0, "order": 0, "span": 2},
                    {"node": "t2", "rank": 1, "order": 0},
                ],
            },
        }
    ],
}


def test_every_field_survives_the_round_trip() -> None:
    model = load(json.dumps(SINK))  # schema-valid, or load raises
    assert model.to_dict() == SINK
    assert Model.from_dict(model.to_dict()) == model


def test_typed_accessors() -> None:
    model = Model.from_dict(SINK)
    assert model.spec.default_relation_type == "uses"
    assert not model.spec.is_c4
    peers = model.spec.relation_types["peers"]
    assert peers.directed is False and peers.sources == ("thing",)
    t1 = model.get("t1")
    assert t1 is not None and t1.docs[1].format == "asciidoc"
    assert model.views[0].layout is not None
    assert model.views[0].layout.placements[0].span == 2
    assert model.relations[0].implied is False
    assert model.parent_of("p1") == "t1" and model.top_of("p1") == "t1"
