"""Deterministic assembly: the MCP builds and validates what the agent drafts.

No LLM, no network. Proves the agent's draft becomes a schema-valid model, that
the fixed spec is injected, and that a malformed draft fails with a reason
rather than being accepted."""
import pytest

from arb_mcp.application.build_model import BuiltModel, build_model
from arb_mcp.domain.loading import ModelError

DRAFT_NODES = [
    {"id": "user", "type": "person", "name": "User", "description": "An end user"},
    {"id": "sys", "type": "softwareSystem", "name": "System", "description": "The system",
     "nodes": [
         {"id": "web", "type": "container", "name": "Web", "description": "UI",
          "technology": "TypeScript"},
     ]},
]
DRAFT_RELS = [{"from": "user", "to": "web", "description": "Uses", "technology": "HTTPS"}]


def test_build_injects_spec_and_validates():
    built = build_model(DRAFT_NODES, DRAFT_RELS, name="Demo")
    assert isinstance(built, BuiltModel)
    assert built.model["spec"]["nodeTypes"]  # spec injected, not supplied by the agent
    assert built.model["nodes"]
    assert isinstance(built.report.may_merge, bool)


def test_missing_relation_type_is_defaulted():
    built = build_model(DRAFT_NODES, DRAFT_RELS)
    assert built.model["relations"][0]["type"] == "uses"  # spec default filled in


def test_malformed_draft_fails_with_a_reason():
    with pytest.raises(ModelError):
        build_model([{"id": "x"}])  # node missing type/name


def test_include_implied_adds_derived_relations_to_validation():
    """The implied-relations branch of the linter must actually run."""
    from arb_mcp.application.validate_model import validate_model as vm
    from arb_mcp.domain.loading import load
    m = load(open("tests/fixtures/agatha.arch").read())
    base = vm(m, include_implied=False)
    derived = vm(m, include_implied=True)
    # deriving relations can only keep or change findings, never crash
    assert isinstance(base.findings, list) and isinstance(derived.findings, list)


def test_describe_contract_returns_spec_and_schema():
    import json

    from arb_mcp.infra.mcp.stdio_server import describe_contract
    out = json.loads(describe_contract())
    assert out["spec"]["nodeTypes"]
    assert out["schema"]["$schema"] if "$schema" in out["schema"] else out["schema"]
