"""HTTP adapter: the same five use cases as stdio, for a CI or a browser.

This is the transport a pipeline calls and the one a demo shows (``/docs`` is the
OpenAPI page). It adds exactly two things stdio does not need: a bearer token, and
one audit line per request. It adds no logic — every endpoint is a thin call into
``application/``; ``domain/`` never learns this file exists. FastAPI is an optional
extra (``pip install arb-mcp[http]``) so the core stays framework-free.

The real MCP transport is mounted too, at ``/mcp`` (streamable HTTP from the SDK),
behind the same token: an MCP host and a REST caller hit the same server.

HTTP status is the only translation this layer makes, and it maps the two kinds of
failure the tools already distinguish:

- structural (the source is not a model)   → 422, body unchanged
- unknown export format                     → 400
- catalog not reachable                     → 503
- a *finding* is not a failure              → 200 with ``may_merge`` in the body
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from ...application.build_model import C4_SPEC, build_model
from ...application.check_catalog import check_catalog
from ...application.convert_model import FORMATS, convert_source
from ...application.validate_model import validate_source
from ...domain import loading
from ...domain.loading import SCHEMA, ModelError
from ..leanix import from_env
from ..mcp.stdio_server import mcp as mcp_server
from .auth import Authenticator, AuthError, StaticTokenAuth

_audit = logging.getLogger("arb_mcp.audit")
_OPEN_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")


# ── request bodies ────────────────────────────────────────────────────────────
class BuildIn(BaseModel):
    nodes: list[dict[str, Any]]
    relations: list[dict[str, Any]] = Field(default_factory=list)
    name: str = ""


class SourceIn(BaseModel):
    source: str


class ValidateIn(SourceIn):
    include_implied: bool = False


class ConvertIn(SourceIn):
    to: str = "drawio"


# ── auth + audit ──────────────────────────────────────────────────────────────
class _Guard(BaseHTTPMiddleware):
    """Authenticate everything but the open paths, and leave one audit line per call.

    A middleware and not a FastAPI dependency on purpose: the MCP transport is a
    mounted sub-app and dependencies do not reach it. This does.

    The guard does not know HOW a caller is verified — a pre-shared token on a
    laptop, a JWT from PingFederate in the bank — it asks the ``Authenticator`` it
    was given and names the caller by what that returns. Swapping the identity
    provider is configuration, not a change here.
    """

    def __init__(self, app: Any, auth: Authenticator) -> None:
        super().__init__(app)
        self._auth = auth

    @staticmethod
    def _rejected(exc: AuthError) -> Response:
        # 401 = not authenticated, 403 = authenticated but not allowed. The detail
        # names the reason in words and never echoes the token.
        kind = "unauthorized" if exc.status == 401 else "forbidden"
        return JSONResponse({"error": kind, "detail": exc.detail}, exc.status)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        t0 = time.perf_counter()
        caller = "anonymous"
        if not request.url.path.startswith(_OPEN_PATHS):
            try:
                caller = self._auth.authenticate(request.headers.get("authorization", "")).subject
            except AuthError as exc:
                response = self._rejected(exc)
                self._log(request, response, t0, caller)
                return response
        response = await call_next(request)
        self._log(request, response, t0, caller)
        return response

    def _log(self, request: Request, response: Response, t0: float, caller: str) -> None:
        _audit.info(json.dumps({
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "caller": caller,
        }))


# ── app ───────────────────────────────────────────────────────────────────────
def create_app(token: str | None = None, *, auth: Authenticator | None = None) -> FastAPI:
    """Build the app around an ``Authenticator``. This surface is never anonymous.

    ``auth`` is the real parameter — an OIDC verifier for the bank's IdP, or a
    static token for a laptop. ``token`` is the shorthand for the latter.
    """
    if auth is None:
        if not token:
            raise RuntimeError("no authenticator: pass auth=, or token= for local development")
        auth = StaticTokenAuth(token)

    # streamable_http_app() must be called before session_manager exists
    mcp_asgi = mcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(
        title="arb-mcp",
        version="0.1.0",
        summary="Deterministic C4/DSL validation, conversion and catalog reconciliation.",
        description=(
            "The same five tools the MCP server exposes over stdio, over HTTP. "
            "Only deterministic validation may block a merge; nothing here calls an LLM."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(_Guard, auth=auth)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "arb-mcp"}

    @app.get("/v1/contract", tags=["tools"])
    def contract() -> dict[str, Any]:
        """The C4 spec and the normative schema a design must satisfy."""
        return {"spec": C4_SPEC, "schema": SCHEMA}

    @app.post("/v1/build", tags=["tools"])
    def build(body: BuildIn) -> Response:
        """Assemble a canonical model from drafted parts; 422 with the reason if malformed."""
        try:
            built = build_model(body.nodes, body.relations, name=body.name)
        except ModelError as exc:
            return JSONResponse(
                {"ok": False, "error": "invalid_model", "detail": str(exc)}, 422
            )
        return JSONResponse(
            {"ok": True, "model": built.model, "validation": built.report.to_dict()}
        )

    @app.post("/v1/validate", tags=["tools"])
    def validate(body: ValidateIn) -> Response:
        """The merge gate. 200 with the verdict; 422 if the source is not a model."""
        try:
            report = validate_source(body.source, include_implied=body.include_implied)
        except ModelError as exc:
            return JSONResponse(
                {"may_merge": False, "error": "invalid_model", "detail": str(exc)}, 422
            )
        return JSONResponse(report.to_dict())

    @app.post("/v1/convert", tags=["tools"])
    def convert(body: ConvertIn) -> Response:
        """Export to drawio (JSON, separate C4 views) or structurizr (raw DSL as text/plain)."""
        try:
            out = convert_source(body.source, body.to)
        except ModelError as exc:
            return JSONResponse(
                {"ok": False, "error": "invalid_model", "detail": str(exc)}, 422
            )
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "formats": list(FORMATS)}, 400
            )
        if body.to == "structurizr":
            return PlainTextResponse(out)
        return Response(out, media_type="application/json")

    @app.post("/v1/catalog", tags=["tools"])
    def catalog(body: SourceIn) -> Response:
        """Reconcile against LeanIX. Informational; 503 when the catalog is not reachable."""
        try:
            model = loading.load(body.source)
            report = check_catalog(model, from_env())
        except ModelError as exc:
            return JSONResponse(
                {"ok": False, "error": "invalid_model", "detail": str(exc)}, 422
            )
        except RuntimeError as exc:
            return JSONResponse(
                {"ok": False, "error": "catalog_unavailable", "detail": str(exc)}, 503
            )
        return JSONResponse({"ok": True, **report.to_dict()})

    app.mount("/mcp", mcp_asgi)
    return app
