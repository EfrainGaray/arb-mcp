"""Ports: interfaces the core needs from the outside world.

Kept as ``Protocol`` so infra adapters are structural implementations with no
import back into application. Deterministic validation needs none of these; a
catalog lookup is an outward, informational step (reconcile the design against
the organization's source of truth) and never touches the merge verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A component as the source-of-truth catalog (LeanIX) knows it."""
    catalog_id: str
    name: str
    type: str


class CatalogPort(Protocol):
    def lookup(self, name: str, kind: str) -> CatalogEntry | None:
        """Return the catalog entry for a component, or None if it is unknown."""
        ...
