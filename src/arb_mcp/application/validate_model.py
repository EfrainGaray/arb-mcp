"""Use case: validate a design and report whether it may merge.

Pure orchestration over the domain — no I/O, no framework. The transport
adapters (stdio, HTTP) call this; they never touch the linter directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain import loading
from ..domain.findings import Finding
from ..domain.linter import lint


@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: list[Finding]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity.blocking]

    @property
    def may_merge(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict[str, Any]:
        return {
            "may_merge": self.may_merge,
            "blocking_count": len(self.blocking),
            "findings": [f.to_dict() for f in self.findings],
        }


def validate_source(text: str, *, include_implied: bool = False) -> ValidationReport:
    """Load ``text`` (any accepted surface) and lint it.

    Raises :class:`arb_mcp.domain.loading.ModelError` if the source cannot be
    turned into a schema-valid model — a structural failure, distinct from a
    lint finding on an otherwise valid model.
    """
    model = loading.load(text)
    findings: list[Finding] = lint(model, include_implied=include_implied)
    return ValidationReport(findings)
