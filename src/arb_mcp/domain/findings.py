"""The typed result of validation.

The ported linter yields ``(severity, rule, message)`` tuples so it can be
diffed line by line against the official Structurizr CLI. That shape is an
implementation detail of the comparison harness; everything above the domain
speaks in ``Finding`` objects instead, where severity is a closed enum and the
subject is addressable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

    @property
    def blocking(self) -> bool:
        """Only ERROR blocks a merge. Nothing probabilistic ever reaches here."""
        return self is Severity.ERROR


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    rule: str
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "severity": self.severity.value,
            "rule": self.rule,
            "message": self.message,
            "blocking": self.severity.blocking,
        }
