"""The typed result of validation.

The ported linter yields ``(severity, rule, message)`` tuples so it can be
diffed line by line against the official Structurizr CLI. That shape is an
implementation detail of the comparison harness; everything above the domain
speaks in ``Finding`` objects instead, where severity is a closed enum and the
subject is addressable.

Subject conventions (``Finding.subject``):
  - element rules (``model.<type>.*``, ``model.id.duplicate``,
    ``model.type.undeclared``, ``model.element.disconnected``): the element id.
  - relation rules (``model.relation.*``): the authored relation id if set,
    else ``"{source}->{target}"``.
  - view rules (``view.*``): the view id.
  - model-level rules (``model.empty``, ``model.scope``): ``""`` (the constant
    ``MODEL`` defined here).

``kw_only`` without a default is deliberate: mypy ``--strict`` turns a
forgotten subject into a build failure instead of a silent empty string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Sentinel for rules that concern the model as a whole, not any single element.
MODEL: str = ""


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
    subject: str = field(kw_only=True)  # no default: every construction must name it

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "severity": self.severity.value,
            "rule": self.rule,
            "subject": self.subject,
            "message": self.message,
            "blocking": self.severity.blocking,
        }
