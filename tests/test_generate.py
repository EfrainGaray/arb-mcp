"""Generation vertical, exercised with a fake LlmPort — no network.

Proves the two invariants that matter for a bank: a valid draft becomes a
schema-valid model with an .arch surface and its own validation report; and a
draft that never validates is rejected, never handed back as if it were real.
"""
import json

import pytest

from arb_mcp.application.generate_model import GeneratedDesign, generate_design
from arb_mcp.domain.loading import ModelError


class FakeLlm:
    def __init__(self, draft):
        self._draft = draft
        self.calls = 0

    def draft_design(self, description, stories):
        self.calls += 1
        return self._draft


GOOD = {
    "nodes": [
        {"id": "user", "type": "person", "name": "User", "description": "An end user"},
        {"id": "sys", "type": "softwareSystem", "name": "System", "description": "The system",
         "nodes": [
             {"id": "web", "type": "container", "name": "Web", "description": "UI",
              "technology": "TypeScript"},
         ]},
    ],
    "relations": [{"from": "user", "to": "web", "description": "Uses", "technology": "HTTPS"}],
    "views": [],
}


def test_generate_produces_valid_arch_and_report():
    design = generate_design(FakeLlm(GOOD), "A system a user talks to", name="Demo")
    assert isinstance(design, GeneratedDesign)
    assert design.model["nodes"]
    assert design.model["spec"]["nodeTypes"]  # spec injected, not invented
    assert isinstance(design.report.may_merge, bool)


def test_generate_is_never_a_gate():
    """The report may say may_merge=false; generation still returns, it never
    raises just because the draft has findings."""
    design = generate_design(FakeLlm(GOOD), "x")
    # even if it has findings, we got a design back
    assert design.model["nodes"]


def test_invalid_draft_is_rejected_after_retries():
    bad = FakeLlm({"nodes": [{"id": "x"}], "relations": [], "views": []})  # node missing type/name
    with pytest.raises(ModelError):
        generate_design(bad, "x", attempts=2)
    assert bad.calls == 2  # it retried, then gave up — never accepted the garbage
