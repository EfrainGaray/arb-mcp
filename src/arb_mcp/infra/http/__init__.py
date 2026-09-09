"""Entry point for the HTTP adapter: ``arb-mcp-http``.

Configuration comes from the environment and nowhere else — no flags, no file —
so a container and a laptop start the same way:

- ``ARB_HTTP_TOKEN``  required; the bearer token every ``/v1/*`` and ``/mcp`` call must carry
- ``ARB_HTTP_HOST``   default ``127.0.0.1``. Bind ``0.0.0.0`` only behind a TLS terminator.
- ``ARB_HTTP_PORT``   default ``8000``
- ``LEANIX_BASE_URL`` / ``LEANIX_API_TOKEN``  only for ``/v1/catalog``
"""
from __future__ import annotations

import logging
import os

from .app import create_app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = create_app(token=os.environ.get("ARB_HTTP_TOKEN", ""))
    uvicorn.run(
        app,
        host=os.environ.get("ARB_HTTP_HOST", "127.0.0.1"),
        port=int(os.environ.get("ARB_HTTP_PORT", "8000")),
        log_level="warning",   # the audit logger is the request log; uvicorn's would duplicate it
    )


if __name__ == "__main__":
    main()
