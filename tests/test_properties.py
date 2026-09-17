"""Invariants over generated models, not examples.

A linter that may block a merge in a bank must be a pure function of the model
and must never crash on a model the schema accepts; the exporters must accept
whatever the linter accepts; and the wire form must survive the typed model.
Hypothesis builds thousands of random schema-valid C4 models to check that, and
shrinks any counterexample to the smallest model that breaks a property."""

from __future__ import annotations

import json
import re
from typing import Any
from xml.etree import ElementTree as ET

from hypothesis import given, settings
from hypothesis import strategies as st

from arb_mcp.application.build_model import C4_SPEC
from arb_mcp.domain import drawio, implied, mermaid, structurizr
from arb_mcp.domain.findings import MODEL as SUBJECT_MODEL
from arb_mcp.domain.linter import lint
from arb_mcp.domain.loading import load
from arb_mcp.domain.model import Model

ident = st.from_regex(r"[a-z][a-z0-9]{0,6}", fullmatch=True)
text = st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=24)
maybe_text = st.one_of(st.none(), text)


def _leaf(kind: str, ids: st.SearchStrategy[str]) -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries(
        {"id": ids, "type": st.just(kind), "name": text},
        optional={"description": text, "technology": text, "tags": st.lists(text, max_size=2)},
    )


@st.composite
def c4_model(draw: st.DrawFn) -> dict[str, Any]:
    """A schema-valid C4 model: persons, systems with containers with components,
    unique ids, relations between any two elements (dangling ones included on
    purpose: the linter must report them, never crash)."""
    ids = draw(st.lists(ident, min_size=1, max_size=12, unique=True))
    pool = list(ids)
    nodes: list[dict[str, Any]] = []
    while pool:
        kind = draw(st.sampled_from(["person", "softwareSystem"]))
        node = draw(_leaf(kind, st.just(pool.pop())))
        wants_children: bool = draw(st.booleans())
        if kind == "softwareSystem" and pool and wants_children:
            containers = []
            for _ in range(draw(st.integers(1, min(3, len(pool))))):
                if not pool:
                    break
                c = draw(_leaf("container", st.just(pool.pop())))
                nests: bool = draw(st.booleans())
                if pool and nests:
                    c["nodes"] = [draw(_leaf("component", st.just(pool.pop())))]
                containers.append(c)
            node["nodes"] = containers
        nodes.append(node)
    endpoints = [*ids, "ghost"]
    relations = draw(
        st.lists(
            st.fixed_dictionaries(
                {"from": st.sampled_from(endpoints), "to": st.sampled_from(endpoints)},
                optional={"type": st.just("uses"), "description": text, "technology": text},
            ),
            max_size=8,
        )
    )
    return {
        "version": "1.0",
        "name": draw(text),
        "scope": draw(st.sampled_from(["system", "landscape", "undefined"])),
        "spec": C4_SPEC,
        "nodes": nodes,
        "relations": relations,
    }


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_linter_is_deterministic_and_total(raw: dict[str, Any]) -> None:
    model = load(json.dumps(raw))
    a = lint(model)
    b = lint(load(json.dumps(raw)))
    assert a == b
    assert lint(model, include_implied=True) == lint(model, include_implied=True)
    dangling = {r["from"] for r in raw["relations"]} | {r["to"] for r in raw["relations"]}
    if "ghost" in dangling:
        assert any(f.rule == "model.relation.endpoint" for f in a)


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_wire_form_survives_the_typed_model(raw: dict[str, Any]) -> None:
    model = Model.from_dict(raw)
    again = Model.from_dict(model.to_dict())
    assert again == model
    assert again.to_dict() == model.to_dict()


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_every_accepted_model_exports_to_well_formed_drawio(raw: dict[str, Any]) -> None:
    model = load(json.dumps(raw))
    for view in drawio.to_views(model):
        root = ET.fromstring(view.xml)  # well-formed
        vertices = {c.get("id") for c in root.iter("mxCell") if c.get("vertex") == "1"}
        vertices |= {o.get("id") for o in root.iter("object")}
        for e in (c for c in root.iter("mxCell") if c.get("edge") == "1"):
            assert e.get("source") in vertices and e.get("target") in vertices


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_structurizr_export_reloads_and_keeps_every_c4_element(raw: dict[str, Any]) -> None:
    model = load(json.dumps(raw))
    reloaded = load(structurizr.to_structurizr(model))
    assert {n.id for n in model.walk()} <= {n.id for n in reloaded.walk()}


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_every_finding_subject_is_addressable(raw: dict[str, Any]) -> None:
    """Every finding carries a subject that is addressable: a model element id,
    a relation 'src->tgt' token, a view id, or '' for model-level rules.
    No element-rule subject is a dotted name path — that is the trap."""
    model = load(json.dumps(raw))
    all_ids = {n.id for n in model.walk()}
    view_ids = {v.id for v in model.views}
    model_level = {"model.empty", "model.scope"}

    for f in lint(model, include_implied=True):
        subject = f.subject
        if f.rule in model_level:
            assert subject == SUBJECT_MODEL, f"{f.rule!r}: expected '' got {subject!r}"
            continue
        # addressable: model element id, relation token, or view id
        is_element = subject in all_ids
        is_relation = (
            "->" in subject
            and len(subject.split("->")) == 2
            and all(isinstance(p, str) for p in subject.split("->"))
        )
        is_view = subject in view_ids
        assert is_element or is_relation or is_view or subject == SUBJECT_MODEL, (
            f"{f.rule!r}: subject {subject!r} is not addressable"
        )
        # element rules must not use dotted name paths (e.g. 'Agatha.Núcleo hexagonal')
        if f.rule.startswith("model.") and not f.rule.startswith("model.relation."):
            assert "." not in subject, (
                f"{f.rule!r}: subject {subject!r} is a dotted path, not an id"
            )


_MERMAID_LINE_PATTERNS = [
    re.compile(r"C4Context|C4Container|C4Component"),
    re.compile(r"\s+title .+"),
    re.compile(r"\s+(Person|System|System_Ext|Container|Container_Ext|Component)\(.+\)"),
    re.compile(r"\s+(System_Boundary|Container_Boundary)\(.+\)\s*\{"),
    re.compile(r"\s+\}"),
    re.compile(r"\s+Rel\(.+\)"),
]


def _any_pattern(line: str) -> bool:
    return any(p.fullmatch(line) for p in _MERMAID_LINE_PATTERNS)


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_every_accepted_model_exports_to_syntactically_closed_mermaid(
    raw: dict[str, Any],
) -> None:
    """Every Mermaid C4 view is syntactically closed: every line matches a
    known pattern, braces balance, and every Rel endpoint is declared in the
    same diagram."""
    model = load(json.dumps(raw))
    for view in mermaid.to_c4_views(model):
        declared: set[str] = set()
        depth = 0
        for line in view.text.splitlines():
            if not line.strip():
                continue
            assert _any_pattern(line), f"unrecognised Mermaid line: {line!r}"
            if line.rstrip().endswith("{"):
                depth += 1
                # extract declared id: first token inside the parentheses
                m = re.search(r"\((\w+),", line)
                if m:
                    declared.add(m.group(1))
            elif line.strip() == "}":
                depth -= 1
            else:
                # non-boundary node or Rel
                m2 = re.search(r"\((\w+),", line)
                if m2 and not line.strip().startswith("Rel("):
                    declared.add(m2.group(1))
        assert depth == 0, f"unbalanced braces in {view.scope!r} view"
        # every Rel endpoint must be declared
        for m3 in re.finditer(r"Rel\((\w+),\s*(\w+),", view.text):
            src, tgt = m3.group(1), m3.group(2)
            assert src in declared, f"Rel source {src!r} not declared in {view.scope!r}"
            assert tgt in declared, f"Rel target {tgt!r} not declared in {view.scope!r}"


@settings(max_examples=40, deadline=None)
@given(c4_model())
def test_implied_relations_never_duplicate_a_pair(raw: dict[str, Any]) -> None:
    model = load(json.dumps(raw))
    derived, n = implied.derive(model)
    pairs = [(r.source, r.target) for r in derived.relations]
    written = len(model.relations)
    assert len(derived.relations) == written + n
    assert len(set(pairs[written:])) == n  # every derived pair is new
    assert not set(pairs[written:]) & set(pairs[:written])
