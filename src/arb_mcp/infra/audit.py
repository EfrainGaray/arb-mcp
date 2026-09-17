"""Request correlation id and structured audit logging, shared by HTTP and stdio.

Stdlib-only: this module must be importable by both transports without pulling in
``mcp`` (the MCP SDK is not a dependency of the HTTP adapter) or any third-party
logging framework.

The single ``arb_mcp.audit`` logger is the request log for both transports:

- HTTP: the guard binds an id per request (from the incoming ``X-Request-ID`` header
  or a freshly minted one), echoes it in the response, and passes it downstream via
  ``request_id`` ContextVar so a tool run under streamable HTTP inherits the same id.
- stdio: each tool wraps its body with ``tool_call()``, which reads the id from the
  ContextVar if one is already bound (HTTP path), from ``ctx.request_id`` (the
  JSON-RPC id on stdio), or mints a fresh one.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

LOGGER = logging.getLogger("arb_mcp.audit")
REQUEST_ID_HEADER = "X-Request-ID"

_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# The active request id for the current task/thread. None when no request is in
# flight (e.g. during startup). The HTTP guard sets it for the duration of a
# request; stdio tools set it for the duration of the tool call.
request_id: ContextVar[str | None] = ContextVar("arb_request_id", default=None)


def new_request_id() -> str:
    """Mint a fresh id: 32 lowercase hex characters (uuid4, no hyphens)."""
    return uuid4().hex


def accept_request_id(given: str | None) -> str:
    """Keep a client-supplied id iff it matches ``^[A-Za-z0-9._-]{1,64}$``; else mint one.

    A hostile header must not be able to inject newlines or JSON fragments into the
    log line. The regex is the only gate: if it passes, the value is used verbatim;
    if not, a fresh uuid4 hex is used instead.
    """
    if given is not None and _ID_RE.match(given):
        return given
    return new_request_id()


def emit(**fields: object) -> None:
    """Log one JSON line on ``arb_mcp.audit`` with ``request_id`` prepended."""
    LOGGER.info(json.dumps({"request_id": request_id.get(), **fields}))


def configure_logging() -> None:
    """One-shot basic config: INFO to stderr, message only.

    ``logging.basicConfig`` is a no-op when a handler is already present — safe to
    call from both ``main()`` entry points and from test setup.
    """
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")


@contextmanager
def tool_call(name: str, ctx: object | None) -> Iterator[None]:
    """Bind a correlation id for the tool body and emit an audit line on exit.

    Precedence for the id, highest first:
    1. An id already bound by the transport (the HTTP guard set ``request_id``).
    2. ``ctx.request_id`` — the JSON-RPC message id injected by the SDK on stdio.
    3. A freshly minted uuid4 hex.

    ``ctx`` is typed ``object | None`` so this module does not import ``mcp``.
    The attribute is read with ``getattr`` so a ``None`` ctx and a ctx with no
    ``request_id`` are both handled gracefully.

    The emitted line carries ``tool``, ``ms``, ``outcome`` (``"ok"`` or
    ``"error:<ExceptionType>"``), and ``request_id``.
    """
    bound = request_id.get()
    if bound is not None:
        # HTTP guard already set it; inherit without touching the ContextVar so
        # the guard's reset stays authoritative.
        token = None
    else:
        raw = getattr(ctx, "request_id", None)
        rid = accept_request_id(str(raw) if raw is not None else None)
        token = request_id.set(rid)

    t0 = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except Exception as exc:
        outcome = f"error:{type(exc).__name__}"
        raise
    finally:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        emit(tool=name, ms=ms, outcome=outcome)
        if token is not None:
            request_id.reset(token)
