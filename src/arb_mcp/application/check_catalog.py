"""Use case: reconcile a design against the architecture catalog (source of truth).

The design says what the team believes exists; the catalog (LeanIX) says what the
organization has on record. This walks the model's real components and asks the
catalog whether each one exists, so a reviewer can see which are known (and their
catalog id) and which are new and must be registered to keep the catalog current.

It is informational: it never blocks a merge. Only deterministic validation does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.model import Model
from .ports import CatalogEntry, CatalogPort

# Canonical types that map to catalog fact sheets. A person or a decision is not
# a catalog component; systems, containers and components are.
_CATALOG_TYPES = {"softwareSystem", "container", "component"}


@dataclass(frozen=True, slots=True)
class CatalogMatch:
    """One model element reconciled against the catalog.

    ``entry`` is set when the catalog recognises the element; ``None`` when it
    does not. ``known`` is the derived property; callers should not inspect
    ``entry is not None`` directly so the intent stays readable.
    """

    id: str
    name: str
    type: str
    entry: CatalogEntry | None  # None = unknown to the catalog

    @property
    def known(self) -> bool:
        return self.entry is not None

    def to_dict(self) -> dict[str, str]:
        """Exactly today's wire keys: id/name/type always; catalog_id/catalog_name when known."""
        out: dict[str, str] = {"id": self.id, "name": self.name, "type": self.type}
        if self.entry is not None:
            out["catalog_id"] = self.entry.catalog_id
            out["catalog_name"] = self.entry.name
        return out


@dataclass(frozen=True, slots=True)
class CatalogReport:
    """All matches for a model, grouped by recognition status.

    ``checked`` is the single source of truth; ``known`` and ``unknown`` are
    derived views over it. ``to_dict()`` produces the same wire keys as before.
    """

    checked: tuple[CatalogMatch, ...]

    @property
    def known(self) -> tuple[CatalogMatch, ...]:
        return tuple(m for m in self.checked if m.known)

    @property
    def unknown(self) -> tuple[CatalogMatch, ...]:
        return tuple(m for m in self.checked if not m.known)

    @property
    def coverage(self) -> float:
        total = len(self.checked)
        return len(self.known) / total if total else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": len(self.checked),
            "known": [m.to_dict() for m in self.known],
            "unknown": [m.to_dict() for m in self.unknown],
            "coverage": round(self.coverage, 3),
        }


def check_catalog(model: Model, catalog: CatalogPort) -> CatalogReport:
    """Look every catalog-relevant component up in the source of truth."""
    matches: list[CatalogMatch] = []
    for n in model.walk():
        if n.type not in _CATALOG_TYPES:
            continue
        entry: CatalogEntry | None = catalog.lookup(n.name, n.type)
        matches.append(CatalogMatch(id=n.id, name=n.name, type=n.type, entry=entry))
    return CatalogReport(checked=tuple(matches))
