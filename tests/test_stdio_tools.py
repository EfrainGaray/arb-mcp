"""The stdio tools speak JSON on every path: success, structural failure, unknown
format, catalog unreachable."""

from __future__ import annotations

import json

import pytest

from arb_mcp.infra.mcp.stdio_server import build_model_tool, check_catalog, convert_model

NODES = [
    {"id": "u", "type": "person", "name": "U", "description": "d"},
    {"id": "s", "type": "softwareSystem", "name": "S", "description": "d"},
]
DSL = 'workspace "w" {\n  model {\n    u = person "U"\n  }\n}\n'


def test_build_tool_returns_model_and_validation() -> None:
    out = json.loads(build_model_tool(NODES, [{"from": "u", "to": "s", "technology": "https"}]))
    assert out["ok"] and out["model"]["relations"][0]["type"] == "uses"
    assert "may_merge" in out["validation"]


def test_build_tool_reports_schema_failure_as_json() -> None:
    out = json.loads(build_model_tool([{"id": "x"}]))
    assert out["ok"] is False and out["error"] == "invalid_model"


def test_convert_tool_unknown_format_lists_the_known_ones() -> None:
    out = json.loads(convert_model(DSL, to="visio"))
    assert out["ok"] is False and "drawio" in out["formats"]


def test_convert_tool_invalid_source_is_json_not_a_crash() -> None:
    out = json.loads(convert_model("garbage", to="drawio"))
    assert out["error"] == "invalid_model"


def test_convert_tool_structurizr_is_text() -> None:
    assert convert_model(DSL, to="structurizr").startswith("workspace")


def test_convert_tool_mermaid_is_json_views() -> None:
    out = json.loads(convert_model(DSL, to="mermaid"))
    views = out["views"]
    assert views, "at least one view"
    assert views[0]["level"] == "C1"
    assert views[0]["mermaid"].startswith("C4Context")
    # every view has the mermaid key, not xml
    assert all("mermaid" in v and "xml" not in v for v in views)


def test_catalog_tool_without_env_is_unavailable_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEANIX_BASE_URL", raising=False)
    monkeypatch.delenv("LEANIX_API_TOKEN", raising=False)
    out = json.loads(check_catalog(DSL))
    assert out["ok"] is False and out["error"] == "catalog_unavailable"
    assert json.loads(check_catalog("garbage"))["error"] == "invalid_model"
