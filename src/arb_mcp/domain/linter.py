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
        findings.append(
            Finding(Severity.ERROR, "model.empty", "The model declares no elements.")
        )

    findings += [
        Finding(Severity(sev), rule, message)
        for sev, rule, message in inspections.inspect(subject)
    ]
    return findings
