"""Inspections over the typed model: the architecture linter's rule set.

Structurizr ships 44 rules hardwired to its types: one demanding documentation
on a "softwareSystem", another decisions, another technology on relations.
They work because its nine types are fixed.

Here types are declared, so the rules cannot name them. They lean on what the
spec SAYS about each type: if a type declares ``requires``, that is a rule; if a
type can contain others, documentation can be demanded once it does. The spec
stops being decorative and becomes the contract that gets checked.

Rewritten over ``Model`` from the vendored engine on 2026-09-09; the golden
fixture ``tests/fixtures/engine_golden.json`` pins the verdicts of the vendored
version so this one cannot drift from what was measured against the official
CLI (16=16 elements, 20=20 relations, 3=3 views).
"""

from __future__ import annotations

from collections.abc import Iterator

from .findings import MODEL, Finding, Severity, subject_of
from .model import Model, Node

_ATTRIBUTE_FIELDS = ("description", "technology", "name")


def _has(node: Node, field: str) -> bool:
    """A required field is satisfied by a first-class attribute or by a property."""
    if field in _ATTRIBUTE_FIELDS:
        return bool(getattr(node, field))
    return bool(node.properties.get(field))


def _paths(nodes: tuple[Node, ...], prefix: str = "") -> Iterator[tuple[Node, str]]:
    for n in nodes:
        path = f"{prefix}.{n.name}" if prefix else n.name
        yield n, path
        yield from _paths(n.nodes, path)


def inspect(model: Model) -> list[Finding]:
    v: list[Finding] = []
    types = model.spec.node_types
    nodes = list(_paths(model.nodes))
    path_of = {n.id: p for n, p in nodes}

    # ── 1. what the spec declares mandatory ──
    for n, path in nodes:
        node_type = types.get(n.type)
        v.extend(
            Finding(
                Severity.ERROR,
                f"model.{n.type}.{field}",
                f'The {n.type} "{path}" does not declare {field}, which its type requires.',
                subject=n.id,
            )
            for field in (node_type.requires if node_type else ())
            if not _has(n, field)
        )

    # ── 2. a node with children should be documented ──
    v.extend(
        Finding(
            Severity.ERROR,
            f"model.{n.type}.documentation",
            f'The {n.type} "{path}" holds {len(n.nodes)} elements inside, but is not documented.',
            subject=n.id,
        )
        for n, path in nodes
        if n.nodes and not n.docs
    )

    # ── 3. a node with children should be backed by some decision ──
    decision_types = {t for t in types if "decision" in t.lower()}
    if decision_types:
        decided = {
            r.target
            for r in model.relations
            if (src := model.get(r.source)) is not None and src.type in decision_types
        }
        v.extend(
            Finding(
                Severity.ERROR,
                f"model.{n.type}.decisions",
                f'The {n.type} "{path}" holds elements inside, but no decision backs it.',
                subject=n.id,
            )
            for n, path in nodes
            if n.nodes and n.id not in decided
        )

    # ── 4. relations with no technology ──
    # DELIBERATE DIVERGENCE from Structurizr, measured in the cross-check: the
    # official inspects derived relations too, so it reports TWO errors for a
    # single missing technology — one on the relation someone wrote and one on
    # the relation the machine inferred. The second cannot be fixed where it
    # appears. Here only what a person wrote is held against them.
    v.extend(
        Finding(
            Severity.ERROR,
            "model.relation.technology",
            f'The relation between "{path_of.get(r.source, r.source)}" and '
            f'"{path_of.get(r.target, r.target)}" declares no technology.',
            subject=subject_of(r),
        )
        for r in model.written_relations()
        if not r.technology
    )

    # ── 5. elements with no description ──
    v.extend(
        Finding(
            Severity.WARNING,
            f"model.{n.type}.description",
            f'The {n.type} "{path}" has no description.',
            subject=n.id,
        )
        for n, path in nodes
        if not n.description
    )

    # ── 6. disconnected elements ──
    touched = {r.source for r in model.relations} | {r.target for r in model.relations}
    v.extend(
        Finding(
            Severity.WARNING,
            "model.element.disconnected",
            f'The element "{path}" relates to nothing.',
            subject=n.id,
        )
        for n, path in nodes
        if n.id not in touched and not n.nodes
    )

    # ── 7. the model should declare its scope ──
    # Equivalent to the official workspace.scope: a field of its own with
    # closed values, NOT the description. Confusing the two was an error in
    # the first cross-check, and it compared two different things.
    if model.scope in ("", "undefined"):
        v.append(
            Finding(
                Severity.ERROR,
                "model.scope",
                'The model does not declare its scope. "landscape" or "system" is recommended.',
                subject=MODEL,
            )
        )

    return v
