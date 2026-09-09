"""The rewritten engine reproduces the vendored one verdict for verdict.

``engine_golden.json`` was recorded from the vendored ``_engine`` on 2026-09-09,
right before it was deleted: inspections with and without implied relations,
the implied relations themselves, and the Structurizr parse of ``simple.dsl``.
The vendored engine had been measured bit-for-bit against the official
Structurizr CLI (16=16, 20=20, 3=3), so equality here carries that measurement
forward to the typed rewrite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arb_mcp.domain import implied, inspections, structurizr_dsl
from arb_mcp.domain.findings import Finding
from arb_mcp.domain.model import Model

FIX = Path(__file__).parent / "fixtures"
GOLD: dict[str, Any] = json.loads((FIX / "engine_golden.json").read_text("utf-8"))


def _tuples(findings: list[Finding]) -> list[list[str]]:
    return [[f.severity.value, f.rule, f.message] for f in findings]


def _model(name: str) -> Model:
    if name.endswith(".dsl"):
        raw, _ = structurizr_dsl.convert((FIX / name).read_text("utf-8"))
        return Model.from_dict(raw)
    return Model.from_dict(json.loads((FIX / name).read_text("utf-8")))


@pytest.mark.parametrize("name", sorted(GOLD))
def test_inspections_match_vendored_engine(name: str) -> None:
    assert _tuples(inspections.inspect(_model(name))) == GOLD[name]["raw"]


@pytest.mark.parametrize("name", sorted(GOLD))
def test_implied_relations_match_vendored_engine(name: str) -> None:
    derived, _n = implied.derive(_model(name))
    assert [r.to_dict() for r in derived.relations] == GOLD[name]["implied_relations"]
    assert _tuples(inspections.inspect(derived)) == GOLD[name]["implied"]


def test_structurizr_parse_matches_vendored_engine() -> None:
    raw, lost = structurizr_dsl.convert((FIX / "simple.dsl").read_text("utf-8"))
    assert raw == GOLD["simple.dsl"]["model"]
    assert lost == GOLD["simple.dsl"]["lost"]
