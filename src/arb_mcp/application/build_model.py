"""Use case: assemble a canonical model from the parts an agent drafted.

The MCP has no LLM and calls none. Kiro (or any MCP host) does the thinking —
it reads the epic and drafts the C4 elements — then hands them here. This is
pure, deterministic assembly: inject the fixed spec so the agent cannot invent
types, hold the result to the schema, and return the model with its validation
report. A malformed draft raises ``ModelError`` with the exact reason, which is
the signal the agent uses to fix its next attempt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from ..domain import loading
from .validate_model import ValidationReport, validate_model

C4_SPEC: dict[str, Any] = json.loads((files("arb_mcp.domain.specs") / "c4.json").read_text("utf-8"))


@dataclass(frozen=True, slots=True)
class BuiltModel:
    model: dict[str, Any]
    report: ValidationReport


def _normalize_relations(relations: list[dict[str, Any]], spec: dict[str, Any]) -> None:
    """Fill a missing relation ``type`` with the spec's default (``uses`` for C4)."""
    rel_types = list((spec.get("relationTypes") or {}).keys())
    if not rel_types:
        return
    for r in relations:
        if not r.get("type"):
            r["type"] = rel_types[0]


def build_model(
    nodes: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None = None,
    *,
    name: str = "",
    spec: dict[str, Any] | None = None,
) -> BuiltModel:
    """Assemble and validate a canonical model from drafted parts.

    Raises :class:`arb_mcp.domain.loading.ModelError` if the parts do not form a
    schema-valid model — the deterministic feedback the caller acts on."""
    spec = spec or C4_SPEC
    relations = [dict(r) for r in (relations or [])]
    _normalize_relations(relations, spec)
    model = {
        "version": "1.0",
        "name": name or "Design",
        "scope": "system",
        "spec": spec,
        "nodes": nodes,
        "relations": relations,
        "views": [],
    }
    loading.validate_schema(model)
    return BuiltModel(model=model, report=validate_model(model))
