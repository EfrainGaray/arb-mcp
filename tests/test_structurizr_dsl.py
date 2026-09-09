"""The Structurizr parser: what it keeps, and what it honestly reports as lost."""

from __future__ import annotations

from arb_mcp.domain import inspections
from arb_mcp.domain.model import Model
from arb_mcp.domain.structurizr_dsl import convert

WORKSPACE = """
workspace "W" "desc" {
    !identifiers hierarchical
    model {
        u = person "User" "" "" "external, vip"
        s = softwareSystem "Sys" "The system" {
            tags "core" "critical"
            description "ignored here"
            url https://example.test
            c = container "C" "" "Go"
        }
        u -> c "Uses" "HTTPS"
        {
        what is this
    }
    views {
        systemContext s "Context" {
            include *
            autolayout lr
        }
        styles {
            element "Person" {
                shape person
            }
        }
        theme default
        nonsense here
    }
}
"""


def test_tags_from_the_fourth_slot_and_the_tags_line_both_land() -> None:
    m, _ = convert(WORKSPACE)
    by_id = {n["id"]: n for n in m["nodes"]}
    assert by_id["u"]["tags"] == ["external", "vip"]
    assert by_id["s"]["tags"] == ["core", "critical"]
    assert by_id["s"]["nodes"][0]["technology"] == "Go"
    assert m["description"] == "desc"


def test_lost_constructs_are_reported_not_hidden() -> None:
    _, lost = convert(WORKSPACE)
    kinds = {x.split(":")[0] for x in lost}
    assert kinds == {
        "directive",
        "element property",
        "unrecognized",
        "style or theme",
        "in views, unrecognized",
    }


def test_view_block_depth_does_not_swallow_the_model() -> None:
    m, _ = convert(WORKSPACE)
    assert [v["title"] for v in m["views"]] == ["Context"]
    assert len(m["relations"]) == 1


def test_required_field_may_live_in_properties_or_as_attribute() -> None:
    m = Model.from_dict(
        {
            "version": "1.0",
            "scope": "system",
            "spec": {
                "nodeTypes": {
                    "decision": {"requires": ["status", "description"]},
                }
            },
            "nodes": [
                {
                    "id": "d1",
                    "type": "decision",
                    "name": "D1",
                    "description": "why",
                    "properties": {"status": "accepted"},
                },
                {"id": "d2", "type": "decision", "name": "D2"},
            ],
        }
    )
    rules = sorted(f.rule for f in inspections.inspect(m) if f.rule.startswith("model.decision."))
    assert rules == [
        "model.decision.description",
        "model.decision.description",
        "model.decision.status",
    ]
