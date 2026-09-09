"""Use case: reconcile a design against the architecture catalog (source of truth).

The design says what the team believes exists; the catalog (LeanIX) says what the
organization has on record. This walks the model's real components and asks the
catalog whether each one exists, so a reviewer can see which are known (and their
catalog id) and which are new and must be registered to keep the catalog current.

It is informational: it never blocks a merge. Only deterministic validation does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ports import CatalogEntry, CatalogPort

# Canonical types that map to catalog fact sheets. A person or a decision is not
# a catalog component; systems, containers and components are.
_CATALOG_TYPES = {"softwareSystem", "container", "component"}


@dataclass(frozen=True, slots=True)
class CatalogReport:
    known: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[dict[str, Any]] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        total = len(self.known) + len(self.unknown)
        return len(self.known) / total if total else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": len(self.known) + len(self.unknown),
            "known": self.known,
            "unknown": self.unknown,
            "coverage": round(self.coverage, 3),
        }


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.get("nodes", [])))
    return out


def check_catalog(model: dict[str, Any], catalog: CatalogPort) -> CatalogReport:
    """Look every catalog-relevant component up in the source of truth."""
    report = CatalogReport()
    for n in _walk(model.get("nodes", [])):
        if n.get("type") not in _CATALOG_TYPES:
            continue
        name = str(n.get("name", n["id"]))
        entry: CatalogEntry | None = catalog.lookup(name, n["type"])
        if entry is None:
            report.unknown.append({"id": n["id"], "name": name, "type": n["type"]})
        else:
            report.known.append(
                {
                    "id": n["id"],
                    "name": name,
                    "type": n["type"],
                    "catalog_id": entry.catalog_id,
                    "catalog_name": entry.name,
                }
            )
    return report
