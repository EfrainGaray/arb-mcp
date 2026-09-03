"""Use case: draft a design from natural language (a prompt, an epic, a file).

This is the probabilistic edge. It NEVER blocks a merge: what it returns is a
draft plus the deterministic validation report of that draft, so a human sees
exactly which rules the generated design still breaks. The spec (type system)
is fixed and injected here — the model only fills in elements — so whatever the
LLM returns is always held against the same schema before it leaves.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from ..domain import loading
from .ports import LlmPort
from .validate_model import ValidationReport, validate_model

_C4_SPEC: dict[str, Any] = json.loads(
    (files("arb_mcp.domain.specs") / "c4.json").read_text("utf-8")
)


@dataclass(frozen=True, slots=True)
class GeneratedDesign:
    """A drafted design as the canonical model plus its deterministic report.

    No text surface here: ``.arch``, Structurizr, Mermaid and drawio are all
    exporters over ``model`` and are requested separately via ``convert``."""

    model: dict[str, Any]
    report: ValidationReport


def _normalize_relations(draft: dict[str, Any], spec: dict[str, Any]) -> None:
    """Fill a missing relation ``type`` with the spec's default.

    The engine only emits a well-formed ``.arch`` relation when it carries a
    type (``a -uses-> b``); an LLM that omits it would otherwise produce a
    design that cannot round-trip. The default is the first declared relation
    type — ``uses`` for C4."""
    rel_types = list((spec.get("relationTypes") or {}).keys())
    if not rel_types:
        return
    default = rel_types[0]
    for r in draft.get("relations", []):
        if not r.get("type"):
            r["type"] = default


def _compose(name: str, draft: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "1.0",
        "name": name or "Generated design",
        "scope": "system",
        "spec": spec,
        "nodes": draft.get("nodes", []),
        "relations": draft.get("relations", []),
        "views": draft.get("views", []),
    }


def generate_design(
    llm: LlmPort,
    description: str,
    *,
    stories: list[str] | None = None,
    name: str = "",
    spec: dict[str, Any] | None = None,
    attempts: int = 2,
) -> GeneratedDesign:
    """Draft a design and return it with its validation report.

    Retries a bounded number of times if the LLM emits something that does not
    survive the schema. A draft that never validates raises ``ModelError`` — an
    invalid design is never handed back as if it were real.
    """
    spec = spec or _C4_SPEC
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        draft = llm.draft_design(description, stories or [])
        _normalize_relations(draft, spec)
        model = _compose(name, draft, spec)
        try:
            loading.validate_schema(model)
        except loading.ModelError as exc:
            last = exc
            continue
        report = validate_model(model)
        return GeneratedDesign(model=model, report=report)
    raise loading.ModelError(f"the drafted design never validated: {last}")
