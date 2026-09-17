"""Unit tests for infra/audit.py — stdlib-only, no network, no framework."""

from __future__ import annotations

import json
import re

import pytest


@pytest.mark.parametrize(
    "bad",
    [
        '\n{"injected": true}',  # newline injection
        "a" * 65,  # too long (> 64 chars)
        "",  # empty string
        "has space",  # space not in allowed chars
        "has!bang",  # ! not in allowed chars
        '{"json":1}',  # braces / JSON injection
        "cr\r",  # carriage return
    ],
)
def test_hostile_ids_are_rejected(bad: str) -> None:
    """A hostile header must not inject newlines/JSON into the log line."""
    from arb_mcp.infra.audit import accept_request_id

    result = accept_request_id(bad)
    # Result must not equal the hostile input
    assert result != bad
    # Result must match the allowed pattern (uuid4().hex = 32 hex chars)
    assert re.match(r"^[A-Za-z0-9._-]{1,64}$", result)


def test_valid_id_is_kept() -> None:
    from arb_mcp.infra.audit import accept_request_id

    assert accept_request_id("ci-42") == "ci-42"
    assert accept_request_id("a" * 64) == "a" * 64  # max length boundary


def test_none_gets_a_fresh_id() -> None:
    from arb_mcp.infra.audit import accept_request_id

    rid = accept_request_id(None)
    assert re.match(r"^[0-9a-f]{32}$", rid)


def test_new_request_id_is_32_hex_chars() -> None:
    from arb_mcp.infra.audit import new_request_id

    rid = new_request_id()
    assert re.match(r"^[0-9a-f]{32}$", rid)


def test_emit_writes_json_with_request_id(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from arb_mcp.infra import audit

    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        token = audit.request_id.set("test-emit-id")
        try:
            audit.emit(tool="validate_model", outcome="ok")
        finally:
            audit.request_id.reset(token)

    lines = [r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["request_id"] == "test-emit-id"
    assert entry["tool"] == "validate_model"
    assert entry["outcome"] == "ok"
