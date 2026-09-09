"""The first vertical: the linter reaches the same verdict through the use case
that the ported engine reaches directly, and the MCP tool speaks JSON on top.
"""

import json
from pathlib import Path

import pytest

from arb_mcp.application.validate_model import validate_source
from arb_mcp.domain._engine import convert, inspections
from arb_mcp.domain.loading import ModelError, load

FIX = Path(__file__).parent / "fixtures"
AGATHA = (FIX / "agatha.arch").read_text("utf-8")


def test_load_agatha_is_schema_valid():
    model = load(AGATHA)
    assert model["nodes"]
    assert "spec" in model


def test_use_case_matches_ported_engine():
    """The typed facade must not change a single verdict of the raw engine."""
    model = convert.text_to_json(AGATHA)
    raw = inspections.inspect(model)  # (severity, rule, message) tuples
    report = validate_source(AGATHA)
    got = [(f.severity.value, f.rule, f.message) for f in report.findings]
    assert got == raw


def test_agatha_has_blocking_findings():
    """Agatha's hexagonal core holds components but is undocumented — an ERROR."""
    report = validate_source(AGATHA)
    assert not report.may_merge
    assert report.blocking
    assert all(f.severity.value == "ERROR" for f in report.blocking)


def test_undeclared_node_type_is_blocking():
    """The spec is the vocabulary. A type it does not declare must not pass the gate.

    Before this rule a node typed "nope" reached may_merge=true and the engine
    minted "model.nope.description" from it (found via the HTTP tests, 2026-09-08).
    """
    from arb_mcp.application.build_model import build_model

    built = build_model([{"id": "x", "type": "nope", "name": "X", "description": "d"}])
    assert not built.report.may_merge
    rules = [f.rule for f in built.report.blocking]
    assert "model.type.undeclared" in rules


def test_undeclared_relation_type_is_blocking():
    from arb_mcp.application.build_model import build_model

    nodes = [
        {"id": "a", "type": "person", "name": "A", "description": "d"},
        {"id": "b", "type": "softwareSystem", "name": "B", "description": "d"},
    ]
    built = build_model(nodes, [{"from": "a", "to": "b", "type": "teleports"}])
    assert "model.relation.type.undeclared" in [f.rule for f in built.report.blocking]


def test_declared_types_do_not_trigger_the_rule():
    """Agatha only uses declared types: the new rule must add nothing to its verdict."""
    report = validate_source(AGATHA)
    assert not [f for f in report.findings if f.rule.endswith("type.undeclared")]


def test_invalid_source_is_a_model_error_not_a_crash():
    with pytest.raises(ModelError):
        load("this is not a design at all {{{")


def test_mcp_tool_returns_json():
    from arb_mcp.infra.mcp.stdio_server import validate_model

    out = json.loads(validate_model(AGATHA))
    assert "may_merge" in out
    assert "findings" in out


SIMPLE_DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_structurizr_surface_loads():
    """Regression for the tuple-unpacking bug: Structurizr DSL must reach a
    schema-valid canonical model, not be rejected wholesale."""
    model = load(SIMPLE_DSL)
    assert model["nodes"]
    report = validate_source(SIMPLE_DSL)
    # a valid workspace produces findings, never a load failure
    assert isinstance(report.findings, list)


def test_arch_with_workspace_word_is_not_misrouted():
    """Regression for substring detection: the word 'workspace' inside a free
    description must not divert an .arch file to the Structurizr converter."""
    poisoned = AGATHA.replace('"Agatha"', '"Agatha workspace"', 1)
    model = load(poisoned)  # must not raise
    assert model["nodes"]


def test_empty_model_cannot_merge():
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
