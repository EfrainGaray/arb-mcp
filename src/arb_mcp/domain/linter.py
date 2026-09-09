"""The deterministic linter, as a typed facade over the ported ``inspections``.

This is the only thing in the whole system allowed to block a merge. It is a
pure function of the model: same model in, same findings out, no clock, no
network, no model weights.
"""

from __future__ import annotations

from typing import Any

from ._engine import implied, inspections
from .findings import Finding, Severity


def lint(model: dict[str, Any], *, include_implied: bool = False) -> list[Finding]:
    """Return the findings for ``model``.

    Derived (``implied``) relations are excluded by default: reporting a defect
    on a relation the author never wrote sends them to a line they cannot fix,
    which is the divergence from Structurizr already measured and chosen.
    """
    subject = model
    if include_implied:
        subject, _ = implied.derive(model)

    findings: list[Finding] = []
    # A design with no elements is schema-valid but says nothing; it must never
    # pass a bank's gate. This rule lives here, in the audited facade, not in the
    # vendored engine.
    if not model.get("nodes"):
        findings.append(Finding(Severity.ERROR, "model.empty", "The model declares no elements."))

    # Integrity the JSON Schema cannot express: every id unique, every relation
    # endpoint an element that exists. Without these a dangling relation reads as
    # may_merge=true yet cannot be drawn, and a duplicate id silently overwrites a
    # diagram cell. Deterministic, blocking, in the audited facade.
    ids: list[str] = []

    def _collect(nodes: list[dict[str, Any]]) -> None:
        for n in nodes:
            ids.append(n["id"])
            _collect(n.get("nodes", []))

    _collect(model.get("nodes", []))
    present = set(ids)

    # The spec is the vocabulary: a type it does not declare is not a typo the
    # reader can forgive, it is an element nothing in the notation can draw or
    # check. Found through the HTTP tests on 2026-09-08: a node typed "nope"
    # reached may_merge=true, and the engine even minted a rule named
    # "model.nope.description" from it. The claim that the injected spec keeps an
    # agent from inventing types was only true if something enforced it. This does.
    spec = model.get("spec") or {}
    node_types = set((spec.get("nodeTypes") or {}).keys())
    rel_types = set((spec.get("relationTypes") or {}).keys())

    def _check_types(nodes: list[dict[str, Any]]) -> None:
        for n in nodes:
            if node_types and n.get("type") not in node_types:
                findings.append(
                    Finding(
                        Severity.ERROR,
                        "model.type.undeclared",
                        f'The element "{n["id"]}" has type "{n.get("type")}", which '
                        f"the spec does not declare.",
                    )
                )
            _check_types(n.get("nodes", []))

    _check_types(model.get("nodes", []))
    if rel_types:
        for rel in model.get("relations", []):
            t = rel.get("type")
            if t is not None and t not in rel_types:
                findings.append(
                    Finding(
                        Severity.ERROR,
                        "model.relation.type.undeclared",
                        f"The relation {rel.get('from')} -> {rel.get('to')} has type "
                        f'"{t}", which the spec does not declare.',
                    )
                )
    findings.extend(
        Finding(
            Severity.ERROR,
            "model.id.duplicate",
            f'The id "{dup}" is declared by more than one element.',
        )
        for dup in sorted({i for i in ids if ids.count(i) > 1})
    )
    for rel in model.get("relations", []):
        if "implied" in (rel.get("tags") or []):
            continue
        for end in ("from", "to"):
            ref = rel.get(end)
            if ref not in present:
                findings.append(
                    Finding(
                        Severity.ERROR,
                        "model.relation.endpoint",
                        f'A relation names {end} "{ref}", which is not an element in the model.',
                    )
                )

    findings += [
        Finding(Severity(sev), rule, message) for sev, rule, message in inspections.inspect(subject)
    ]
    return findings
