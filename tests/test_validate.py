"""The first vertical: the linter reaches the same verdict through the use case
that the ported engine reaches directly, and the MCP tool speaks JSON on top.
"""
import json
from pathlib import Path

import pytest

from arb_mcp.application.validate_model import validate_source
from arb_mcp.domain._engine import convert, inspections
from arb_mcp.domain.loading import ModelError, load

FIX = Path(__file__).parent / "fixtures"
AGATHA = (FIX / "agatha.arch").read_text("utf-8")


def test_load_agatha_is_schema_valid():
    model = load(AGATHA)
    assert model["nodes"]
    assert "spec" in model


def test_use_case_matches_ported_engine():
    """The typed facade must not change a single verdict of the raw engine."""
    model = convert.text_to_json(AGATHA)
    raw = inspections.inspect(model)  # (severity, rule, message) tuples
    report = validate_source(AGATHA)
    got = [(f.severity.value, f.rule, f.message) for f in report.findings]
    assert got == raw


def test_agatha_has_blocking_findings():
    """Agatha's hexagonal core holds components but is undocumented — an ERROR."""
    report = validate_source(AGATHA)
    assert not report.may_merge
    assert report.blocking
    assert all(f.severity.value == "ERROR" for f in report.blocking)


def test_invalid_source_is_a_model_error_not_a_crash():
    with pytest.raises(ModelError):
        load("this is not a design at all {{{")


def test_mcp_tool_returns_json():
    from arb_mcp.infra.mcp.stdio_server import validate_model

    out = json.loads(validate_model(AGATHA))
    assert "may_merge" in out
    assert "findings" in out
