"""The tool line must carry the id of the POST that carried the call.

This is the regression test for the ALTO finding of docs/AUDIT-2026-09-17.md. The
first version of the correlation read an already-bound ContextVar, and under the
mounted MCP that variable belongs to the task the SDK starts inside the very first
request of the session (``initialize``): every later ``tools/call`` logged the id of
that first POST forever. A unit test that sets the ContextVar by hand cannot see the
defect, because the defect is in which id the transport hands over.

So this drives the real thing: the SDK's streamable HTTP client against the real app
over an in-process ASGI transport, with a different ``X-Request-ID`` on every POST.
The assertion is that the tool line carries the id of the ``tools/call`` POST and not
the id of ``initialize``.
"""

from __future__ import annotations

import json
import logging
from itertools import count
from typing import Any

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arb_mcp.infra.http.app import create_app

TOKEN = "test-token-not-a-secret"
BASE = "http://127.0.0.1:8000"  # the SDK's DNS-rebinding guard only trusts its configured host
DSL = 'workspace {\n  model {\n    u = person "User"\n  }\n}\n'


@pytest.fixture
def anyio_backend() -> str:
    """anyio ships the pytest plugin; asyncio is the loop uvicorn would use."""
    return "asyncio"


@pytest.mark.anyio
async def test_the_tool_line_carries_the_id_of_the_call_not_of_initialize(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(token=TOKEN)
    numbered = count(1)
    sent: list[str] = []

    async def stamp(request: Any) -> None:
        rid = f"itest-{next(numbered)}"
        request.headers["X-Request-ID"] = rid
        sent.append(rid)

    client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url=BASE,
        headers={"Authorization": f"Bearer {TOKEN}"},
        event_hooks={"request": [stamp]},
        follow_redirects=True,
    )

    # ASGITransport does not run the lifespan, and the mounted MCP session manager
    # starts there; without this the first POST answers 404.
    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        async with (
            app.router.lifespan_context(app),
            streamable_http_client(f"{BASE}/mcp/mcp", http_client=client) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            primera = len(sent)
            await session.call_tool("validate_model", {"source": DSL})
            segunda = len(sent)
            await session.call_tool("validate_model", {"source": DSL})

    lines = [json.loads(r.message) for r in caplog.records if r.name == "arb_mcp.audit"]
    tool_lines = [line for line in lines if line.get("tool") == "validate_model"]
    assert len(tool_lines) == 2, lines
    # Each tool line must carry an id minted for its own POST: the first call's ids
    # start at `primera`, the second call's at `segunda`. The defect this pins made
    # every call reuse the id captured when the session task was born.
    assert tool_lines[0]["request_id"] in sent[primera:segunda]
    assert tool_lines[1]["request_id"] in sent[segunda:]
    assert tool_lines[0]["request_id"] != tool_lines[1]["request_id"]
