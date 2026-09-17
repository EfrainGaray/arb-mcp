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


# ── audit / correlation id ────────────────────────────────────────────────────
def test_tool_call_leaves_one_audit_line_with_tool_name_and_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from arb_mcp.infra.mcp.stdio_server import validate_model

    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        validate_model(DSL)

    lines = [r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool"] == "validate_model"
    assert entry["outcome"] == "ok"
    assert entry.get("request_id")


def test_tool_inherits_the_transport_request_id_when_one_is_bound(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """request.state.request_id (set by the HTTP guard) beats ctx.request_id.

    The guard writes the id to Request.state per-request rather than to a ContextVar
    that would be inherited at asyncio task creation during initialize.  This means
    every tools/call sees the *current* request's id regardless of when the session
    task was spawned.
    """
    import logging

    from arb_mcp.infra.mcp.stdio_server import validate_model

    class _FakeState:
        request_id = "http-7"

    class _FakeRequest:
        state = _FakeState()

    class _FakeRequestContext:
        request = _FakeRequest()

    class _FakeCtx:
        request_context = _FakeRequestContext()
        request_id = "jsonrpc-99"  # lower priority; must not win

    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        validate_model(DSL, ctx=_FakeCtx())  # type: ignore[arg-type]

    entry = json.loads(next(r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"))
    assert entry["request_id"] == "http-7"


def test_tool_uses_the_jsonrpc_id_on_stdio(caplog: pytest.LogCaptureFixture) -> None:
    """A fake ctx with request_id='17' is used when no transport id is bound."""
    import logging

    from arb_mcp.infra.mcp.stdio_server import validate_model

    class _FakeCtx:
        request_id = "17"

    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        validate_model(DSL, ctx=_FakeCtx())  # type: ignore[arg-type]

    entry = json.loads(next(r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"))
    assert entry["request_id"] == "17"


def test_invalid_model_is_outcome_ok_not_error(caplog: pytest.LogCaptureFixture) -> None:
    """A ModelError turned into a JSON answer is a normal outcome.

    Only an escaped exception (not caught inside the tool) is ``error:<Type>``.
    """
    import logging

    from arb_mcp.infra.mcp.stdio_server import validate_model

    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        out = json.loads(validate_model("garbage"))

    assert out.get("error") == "invalid_model"
    entry = json.loads(next(r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"))
    assert entry["outcome"] == "ok"


def test_ctx_is_not_in_the_tool_input_schema() -> None:
    """The SDK must strip 'ctx' from the published tool input schemas."""
    from arb_mcp.infra.mcp.stdio_server import mcp

    # mcp.list_tools() is async; in this sync test suite we reach the same data
    # through the internal ToolManager.  That method is sync in SDK 1.26.0 —
    # verified in .venv/lib/…/mcp/server/mcpserver/server.py.
    tools = mcp._tool_manager.list_tools()
    for tool in tools:
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "ctx" not in props, f"tool {tool.name!r} exposes 'ctx' in its schema"
