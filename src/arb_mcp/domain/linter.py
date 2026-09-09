"""The deterministic linter, as a typed facade over the ported ``inspections``.

This is the only thing in the whole system allowed to block a merge. It is a
pure function of the model: same model in, same findings out, no clock, no
network, no model weights.
"""

from __future__ import annotations

from ._engine import implied, inspections
from .findings import Finding, Severity
from .model import Model


def lint(model: Model, *, include_implied: bool = False) -> list[Finding]:
    """Return the findings for ``model``.

    Derived (``implied``) relations are excluded by default: reporting a defect
    on a relation the author never wrote sends them to a line they cannot fix,
    which is the divergence from Structurizr already measured and chosen.
    """
    findings: list[Finding] = []
    # A design with no elements is schema-valid but says nothing; it must never
    # pass a bank's gate. This rule lives here, in the audited facade, not in the
    # vendored engine.
    if not model.nodes:
        findings.append(Finding(Severity.ERROR, "model.empty", "The model declares no elements."))

    # Integrity the JSON Schema cannot express: every id unique, every relation
    # endpoint an element that exists. Without these a dangling relation reads as
    # may_merge=true yet cannot be drawn, and a duplicate id silently overwrites a
    # diagram cell. Deterministic, blocking, in the audited facade.
    ids = [n.id for n in model.walk()]

    # The spec is the vocabulary: a type it does not declare is not a typo the
    # reader can forgive, it is an element nothing in the notation can draw or
    # check. Found through the HTTP tests on 2026-09-08: a node typed "nope"
    # reached may_merge=true, and the engine even minted a rule named
    # "model.nope.description" from it. The claim that the injected spec keeps an
    # agent from inventing types was only true if something enforced it. This does.
    node_types = model.spec.node_types
    rel_types = model.spec.relation_types
    if node_types:
        findings.extend(
            Finding(
                Severity.ERROR,
                "model.type.undeclared",
                f'The element "{n.id}" has type "{n.type}", which the spec does not declare.',
            )
            for n in model.walk()
            if n.type not in node_types
        )
    if rel_types:
        findings.extend(
            Finding(
                Severity.ERROR,
                "model.relation.type.undeclared",
                f'The relation {r.source} -> {r.target} has type "{r.type}", which the spec '
                f"does not declare.",
            )
            for r in model.relations
            if r.type and r.type not in rel_types
        )
    findings.extend(
        Finding(
            Severity.ERROR,
            "model.id.duplicate",
            f'The id "{dup}" is declared by more than one element.',
        )
        for dup in sorted({i for i in ids if ids.count(i) > 1})
    )
    for rel in model.written_relations():
        for end, ref in (("from", rel.source), ("to", rel.target)):
            if ref not in model:
                findings.append(
                    Finding(
                        Severity.ERROR,
                        "model.relation.endpoint",
                        f'A relation names {end} "{ref}", which is not an element in the model.',
                    )
                )

    # The vendored engine still reads the wire form; it is fed through to_dict()
    # here and nowhere else.
    subject = model.to_dict()
    if include_implied:
        subject, _ = implied.derive(subject)
    findings += [
        Finding(Severity(sev), rule, message) for sev, rule, message in inspections.inspect(subject)
    ]
    return findings
