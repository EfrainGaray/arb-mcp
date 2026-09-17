"""Executable specification of the merge gate, in the reviewers' words.

Each scenario in ``features/merge_gate.feature`` is a rule the architecture
review board can read and sign off without opening the code; pytest-bdd runs it
against the real linter. Gherkin is used ONLY for the deterministic gate, whose
vocabulary is closed and whose verdicts are binary — the properties that make a
scenario table honest. Exporters and transports stay on plain pytest."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from arb_mcp.application.build_model import C4_SPEC
from arb_mcp.application.validate_model import ValidationReport, validate_model
from arb_mcp.domain.loading import from_dict

scenarios("features/merge_gate.feature")


class Draft:
    def __init__(self) -> None:
        self.spec: dict[str, Any] = {}
        self.nodes: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []
        self.views: list[dict[str, Any]] = []
        self.scope = "system"
        self.reports: list[ValidationReport] = []

    def find(self, name: str) -> dict[str, Any]:
        def walk(ns: list[dict[str, Any]]) -> dict[str, Any] | None:
            for n in ns:
                if n["name"] == name:
                    return n
                found = walk(n.get("nodes", []))
                if found:
                    return found
            return None

        node = walk(self.nodes)
        assert node is not None, name
        return node

    def validate(self) -> ValidationReport:
        model = from_dict(
            {
                "version": "1.0",
                "name": "spec",
                "scope": self.scope,
                "spec": self.spec,
                "nodes": self.nodes,
                "relations": self.relations,
                "views": self.views,
            }
        )
        report = validate_model(model)
        self.reports.append(report)
        return report


@pytest.fixture
def draft() -> Draft:
    return Draft()


def _ident(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum()).lower() or "x"


@given("the C4 spec")
def _spec(draft: Draft) -> None:
    draft.spec = C4_SPEC


@given(parsers.parse('a person "{name}"'))
def _person(draft: Draft, name: str) -> None:
    draft.nodes.append({"id": _ident(name), "type": "person", "name": name})


@given(parsers.parse('a person "{name}" described as "{desc}"'))
def _person_desc(draft: Draft, name: str, desc: str) -> None:
    draft.nodes.append({"id": _ident(name), "type": "person", "name": name, "description": desc})


@given(parsers.parse('a software system "{name}"'))
def _system(draft: Draft, name: str) -> None:
    draft.nodes.append({"id": _ident(name), "type": "softwareSystem", "name": name})


@given(
    parsers.parse(
        'a software system "{sys}" with a container "{cont}" that holds a component "{comp}"'
    )
)
def _system_tree(draft: Draft, sys: str, cont: str, comp: str) -> None:
    draft.nodes.append(
        {
            "id": _ident(sys),
            "type": "softwareSystem",
            "name": sys,
            "docs": [{"title": sys, "content": "..."}],
            "nodes": [
                {
                    "id": _ident(cont),
                    "type": "container",
                    "name": cont,
                    "nodes": [{"id": _ident(comp), "type": "component", "name": comp}],
                }
            ],
        }
    )


@given(parsers.parse('an element "{name}" of type "{kind}"'))
def _typed(draft: Draft, name: str, kind: str) -> None:
    draft.nodes.append({"id": _ident(name), "type": kind, "name": name})


@given(parsers.parse('a decision "{name}" that affects "{a}" and "{b}"'))
def _decision2(draft: Draft, name: str, a: str, b: str) -> None:
    _decision(draft, name, a)
    draft.relations.append(
        {"from": _ident(name), "to": _ident(b), "type": "affects", "technology": "ADR"}
    )


@given(parsers.parse('a decision "{name}" that affects "{a}"'))
def _decision(draft: Draft, name: str, a: str) -> None:
    draft.nodes.append(
        {
            "id": _ident(name),
            "type": "decision",
            "name": name,
            "description": "why",
            "properties": {"status": "accepted"},
        }
    )
    draft.relations.append(
        {"from": _ident(name), "to": _ident(a), "type": "affects", "technology": "ADR"}
    )


@given(parsers.parse('a relation from "{a}" to "{b}" over "{tech}"'))
def _relation_tech(draft: Draft, a: str, b: str, tech: str) -> None:
    draft.relations.append({"from": _ident(a), "to": _ident(b), "technology": tech})


@given(parsers.parse('a relation from "{a}" to "{b}"'))
def _relation(draft: Draft, a: str, b: str) -> None:
    draft.relations.append({"from": _ident(a), "to": _ident(b)})


@given("every element is described and every relation names its technology")
def _complete(draft: Draft) -> None:
    def walk(ns: list[dict[str, Any]]) -> None:
        for n in ns:
            n.setdefault("description", "described")
            walk(n.get("nodes", []))

    walk(draft.nodes)
    for r in draft.relations:
        r.setdefault("technology", "HTTPS")


@given(parsers.parse('a view "{vid}" inside "{node}"'))
def _view_inside(draft: Draft, vid: str, node: str) -> None:
    draft.views.append({"id": vid, "title": vid, "include": [{"inside": _ident(node)}]})


@given(parsers.parse('a view "{vid}" of type "{kind}"'))
def _view_type(draft: Draft, vid: str, kind: str) -> None:
    draft.views.append({"id": vid, "title": vid, "include": [{"type": kind}]})


@given(parsers.parse('the model scope is "{scope}"'))
def _scope(draft: Draft, scope: str) -> None:
    draft.scope = scope


@when("the design is validated")
def _validate(draft: Draft) -> None:
    draft.validate()


@when("the design is validated twice")
def _validate_twice(draft: Draft) -> None:
    draft.validate()
    draft.validate()


@then("it may not merge")
def _blocked(draft: Draft) -> None:
    assert draft.reports[-1].may_merge is False


@then("it may merge")
def _allowed(draft: Draft) -> None:
    assert draft.reports[-1].may_merge is True


@then(parsers.parse('the findings include {severity} "{rule}"'))
def _finding(draft: Draft, severity: str, rule: str) -> None:
    hits = [f for f in draft.reports[-1].findings if f.rule == rule]
    assert hits, f"no finding for {rule}"
    assert {f.severity.value for f in hits} == {severity}


@then("both verdicts are identical")
def _same(draft: Draft) -> None:
    a, b = draft.reports[-2:]
    assert a == b


@then(parsers.parse('the verdict on "{rule}" is {verdict}'))
def _verdict(draft: Draft, rule: str, verdict: str) -> None:
    hits = [f.severity.value for f in draft.reports[-1].findings if f.rule == rule]
    assert hits == ([] if verdict == "absent" else [verdict])


@then(parsers.parse('the finding "{rule}" points at "{subject}"'))
def _points_at(draft: Draft, rule: str, subject: str) -> None:
    hits = [f for f in draft.reports[-1].findings if f.rule == rule]
    assert hits, f"no finding for {rule}"
    assert any(f.subject == subject for f in hits), (
        f"no finding for {rule!r} points at {subject!r}; "
        f"subjects found: {[f.subject for f in hits]}"
    )
