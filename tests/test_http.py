"""The HTTP adapter: same use cases as stdio, behind a bearer token, with an audit line.

Written before the adapter (bug = failing test first). Every test drives the app
through Starlette's TestClient so the lifespan — which starts the mounted MCP session
manager — runs exactly as it would under uvicorn.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from arb_mcp.infra.http.app import create_app

TOKEN = "test-token-not-a-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

NODES = [
    {"id": "cust", "type": "person", "name": "Customer", "description": "Pays"},
    {"id": "bill", "type": "softwareSystem", "name": "Billing", "description": "Charges",
     "nodes": [{"id": "api", "type": "container", "name": "API",
                "description": "REST", "technology": "FastAPI"}]},
]
RELS = [{"from": "cust", "to": "api", "description": "Pays", "technology": "HTTPS"}]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(token=TOKEN))


def _model(client: TestClient) -> str:
    r = client.post("/v1/build", json={"nodes": NODES, "relations": RELS, "name": "Billing"},
                    headers=AUTH)
    assert r.status_code == 200, r.text
    return json.dumps(r.json()["model"])


# ── auth ──────────────────────────────────────────────────────────────────────
def test_health_is_open(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_v1_without_token_is_401(client: TestClient) -> None:
    assert client.get("/v1/contract").status_code == 401


def test_v1_with_wrong_token_is_401(client: TestClient) -> None:
    r = client.get("/v1/contract", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_mcp_mount_is_protected_too(client: TestClient) -> None:
    """The MCP transport is mounted under the same token: no anonymous MCP."""
    assert client.post("/mcp", json={}).status_code == 401


def test_app_refuses_to_start_without_token() -> None:
    with pytest.raises(RuntimeError):
        create_app(token="")


# ── the five tools over REST ──────────────────────────────────────────────────
def test_contract_returns_spec_and_schema(client: TestClient) -> None:
    r = client.get("/v1/contract", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "person" in body["spec"]["nodeTypes"] and "$schema" in body["schema"]


def test_build_returns_model_and_verdict(client: TestClient) -> None:
    r = client.post("/v1/build", json={"nodes": NODES, "relations": RELS}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and "may_merge" in body["validation"]
    assert body["model"]["spec"]["nodeTypes"]          # the fixed spec was injected


def test_build_malformed_is_422_with_the_schema_reason(client: TestClient) -> None:
    """A node without name or type cannot become a model at all: structural, 422."""
    r = client.post("/v1/build", json={"nodes": [{"id": "x"}]}, headers=AUTH)
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False and body["error"] == "invalid_model" and body["detail"]


def test_build_unknown_type_is_a_finding_not_a_structural_failure(client: TestClient) -> None:
    """An undeclared type is a schema-valid model that breaks a rule: 200 and may_merge false.

    The two kinds of failure must stay distinct over HTTP exactly as they are in the
    tools: a host fixes a 422 and re-sends; a 200 with a blocking finding is the
    design's verdict."""
    r = client.post("/v1/build", json={"nodes": [{"id": "x", "type": "nope", "name": "X"}]},
                    headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["validation"]["may_merge"] is False


def test_validate_reports_the_gate(client: TestClient) -> None:
    src = _model(client)
    r = client.post("/v1/validate", json={"source": src, "include_implied": True}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"may_merge", "blocking_count", "findings"}
    assert body["may_merge"] == (body["blocking_count"] == 0)


def test_validate_garbage_is_422(client: TestClient) -> None:
    r = client.post("/v1/validate", json={"source": "garbage {{{"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["may_merge"] is False


def test_convert_drawio_returns_separate_views(client: TestClient) -> None:
    src = _model(client)
    r = client.post("/v1/convert", json={"source": src, "to": "drawio"}, headers=AUTH)
    assert r.status_code == 200
    views = r.json()["views"]
    assert [v["level"] for v in views][:2] == ["C1", "C2"]
    assert all(v["xml"].startswith("<mxfile") for v in views)


def test_convert_structurizr_returns_raw_dsl(client: TestClient) -> None:
    src = _model(client)
    r = client.post("/v1/convert", json={"source": src, "to": "structurizr"}, headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text.lstrip().startswith("workspace")


def test_convert_unknown_format_is_400(client: TestClient) -> None:
    src = _model(client)
    r = client.post("/v1/convert", json={"source": src, "to": "png"}, headers=AUTH)
    assert r.status_code == 400 and r.json()["formats"] == ["drawio", "structurizr"]


def test_catalog_without_leanix_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEANIX_BASE_URL", raising=False)
    monkeypatch.delenv("LEANIX_API_TOKEN", raising=False)
    src = _model(client)
    r = client.post("/v1/catalog", json={"source": src}, headers=AUTH)
    assert r.status_code == 503 and r.json()["error"] == "catalog_unavailable"


# ── audit ─────────────────────────────────────────────────────────────────────
def test_every_call_leaves_one_audit_line_without_the_token(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        client.get("/v1/contract", headers=AUTH)
    lines = [r.getMessage() for r in caplog.records if r.name == "arb_mcp.audit"]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["path"] == "/v1/contract" and entry["status"] == 200
    assert "caller" in entry and TOKEN not in lines[0]     # never log the secret


def test_audit_caller_is_who_called_not_who_is_configured(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    """A wrong token must not be logged under the legitimate caller's id.

    Found live on the first deployment: every line carried the same caller, because
    the id was derived from the server's token instead of the presented one."""
    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        client.get("/v1/contract", headers=AUTH)
        client.get("/v1/contract", headers={"Authorization": "Bearer nope"})
        client.get("/v1/contract")
    entries = [json.loads(r.getMessage()) for r in caplog.records if r.name == "arb_mcp.audit"]
    assert [e["status"] for e in entries] == [200, 401, 401]
    assert entries[0]["caller"] != entries[1]["caller"]
    assert entries[2]["caller"] == "anonymous"
