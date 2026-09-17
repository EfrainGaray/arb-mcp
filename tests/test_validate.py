"""The first vertical: the linter reaches the same verdict through the use case
that the ported engine reaches directly, and the MCP tool speaks JSON on top.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from arb_mcp.application.validate_model import validate_source
from arb_mcp.domain import inspections
from arb_mcp.domain.loading import ModelError, load
from arb_mcp.domain.model import Model

FIX = Path(__file__).parent / "fixtures"
AGATHA = (FIX / "agatha.json").read_text("utf-8")


def test_load_agatha_is_schema_valid() -> None:
    model = load(AGATHA)
    assert model.nodes
    assert model.spec.node_types


def test_use_case_matches_ported_engine() -> None:
    """The linter facade adds its integrity rules and otherwise changes no verdict."""
    raw = inspections.inspect(Model.from_dict(json.loads(AGATHA)))
    report = validate_source(AGATHA)
    assert report.findings[-len(raw) :] == raw


def test_agatha_has_blocking_findings() -> None:
    """Agatha's hexagonal core holds components but is undocumented — an ERROR."""
    report = validate_source(AGATHA)
    assert not report.may_merge
    assert report.blocking
    assert all(f.severity.value == "ERROR" for f in report.blocking)


def test_undeclared_node_type_is_blocking() -> None:
    """The spec is the vocabulary. A type it does not declare must not pass the gate.

    Before this rule a node typed "nope" reached may_merge=true and the engine
    minted "model.nope.description" from it (found via the HTTP tests, 2026-09-08).
    """
    from arb_mcp.application.build_model import build_model

    built = build_model([{"id": "x", "type": "nope", "name": "X", "description": "d"}])
    assert not built.report.may_merge
    rules = [f.rule for f in built.report.blocking]
    assert "model.type.undeclared" in rules


def test_undeclared_relation_type_is_blocking() -> None:
    from arb_mcp.application.build_model import build_model

    nodes = [
        {"id": "a", "type": "person", "name": "A", "description": "d"},
        {"id": "b", "type": "softwareSystem", "name": "B", "description": "d"},
    ]
    built = build_model(nodes, [{"from": "a", "to": "b", "type": "teleports"}])
    assert "model.relation.type.undeclared" in [f.rule for f in built.report.blocking]


def test_declared_types_do_not_trigger_the_rule() -> None:
    """Agatha only uses declared types: the new rule must add nothing to its verdict."""
    report = validate_source(AGATHA)
    assert not [f for f in report.findings if f.rule.endswith("type.undeclared")]


def test_invalid_source_is_a_model_error_not_a_crash() -> None:
    with pytest.raises(ModelError):
        load("this is not a design at all {{{")


def test_mcp_tool_returns_json() -> None:
    from arb_mcp.infra.mcp.stdio_server import validate_model

    out = json.loads(validate_model(AGATHA))
    assert "may_merge" in out
    assert "findings" in out


def test_to_dict_carries_subject() -> None:
    """Every finding serialised to a dict must carry a 'subject' key."""
    report = validate_source(AGATHA)
    for f in report.findings:
        d = f.to_dict()
        assert "subject" in d, f"finding {f.rule!r} has no 'subject' key in to_dict()"
        assert isinstance(d["subject"], str)


SIMPLE_DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_structurizr_surface_loads() -> None:
    """Regression for the tuple-unpacking bug: Structurizr DSL must reach a
    schema-valid canonical model, not be rejected wholesale."""
    model = load(SIMPLE_DSL)
    assert model.nodes
    report = validate_source(SIMPLE_DSL)
    # a valid workspace produces findings, never a load failure
    assert isinstance(report.findings, list)


def test_plain_text_is_refused_not_guessed() -> None:
    """Only two surfaces exist. Anything else is a ModelError that names them,
    never a parse attempt on a hunch."""
    with pytest.raises(ModelError, match="Structurizr"):
        load("model Something {\n}")


def test_leading_comment_before_workspace_is_still_structurizr() -> None:
    dsl = "// a comment\n" + SIMPLE_DSL
    assert load(dsl).nodes


def test_typed_model_round_trips_the_wire_form() -> None:
    """from_dict(d).to_dict() keeps every fact of every fixture: the typed model
    is a mirror of the schema, not a lossy view of it."""
    from arb_mcp.domain.model import Model

    for name in ("agatha.json", "despliegue.json", "uml-casos-uso.json"):
        raw = json.loads((FIX / name).read_text("utf-8"))
        again = Model.from_dict(raw).to_dict()
        assert Model.from_dict(again) == Model.from_dict(raw), name
        assert _facts(again) == _facts(raw), name


def _facts(d: Any) -> Any:
    """A dict with its empty optionals dropped, so absent and empty compare equal."""
    if isinstance(d, dict):
        return {k: _facts(v) for k, v in d.items() if v not in (None, "", [], {})}
    if isinstance(d, list):
        return [_facts(x) for x in d]
    return d


def test_authored_relation_id_is_the_subject() -> None:
    """When a relation has an id, findings about it must use that id, not 'src->tgt'."""
    from arb_mcp.domain.findings import subject_of
    from arb_mcp.domain.model import Relation

    r_with_id = Relation(source="a", target="b", id="r1")
    r_without = Relation(source="a", target="b")
    assert subject_of(r_with_id) == "r1"
    assert subject_of(r_without) == "a->b"

    # A relation with id=r1 and no technology triggers a finding whose subject is "r1".
    from arb_mcp.application.build_model import build_model

    nodes = [
        {"id": "a", "type": "person", "name": "A", "description": "d"},
        {"id": "b", "type": "softwareSystem", "name": "B", "description": "d"},
    ]
    built = build_model(nodes, [{"from": "a", "to": "b", "id": "r1"}])
    tech_findings = [f for f in built.report.findings if f.rule == "model.relation.technology"]
    assert tech_findings, "expected a technology finding"
    assert tech_findings[0].subject == "r1"


def test_empty_model_cannot_merge() -> None:
    """Regression: a schema-valid model with zero nodes must be blocked."""
    empty = json.dumps(
        {
            "version": "1.0",
            "name": "x",
            "scope": "system",
            "spec": {"nodeTypes": {"person": {"contains": []}}},
            "nodes": [],
            "relations": [],
        }
    )
    report = validate_source(empty)
    assert not report.may_merge
    assert any(f.rule == "model.empty" for f in report.blocking)
