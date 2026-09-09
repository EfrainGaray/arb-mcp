"""Entry point for the HTTP adapter: ``arb-mcp-http``.

Configuration comes from the environment and nowhere else — no flags, no file —
so a container and a laptop start the same way. Exactly one authentication mode:

- ``ARB_OIDC_ISSUER``    the identity provider (PingFederate, PingOne, Keycloak, Entra…);
                          tokens must be JWTs it signed, found through OIDC discovery
- ``ARB_OIDC_AUDIENCE``  required with the issuer; the ``aud`` a token must carry
- ``ARB_OIDC_SCOPE``     optional; a scope the token must carry (403 without it)
- ``ARB_OIDC_JWKS_URL``  optional; skips discovery when the IdP's JWKS is at a fixed URL
- ``ARB_HTTP_TOKEN``     development only: one pre-shared token. Refused together with the issuer.

- ``ARB_HTTP_HOST``   default ``127.0.0.1``. Bind ``0.0.0.0`` only behind a TLS terminator.
- ``ARB_HTTP_PORT``   default ``8000``
- ``LEANIX_BASE_URL`` / ``LEANIX_API_TOKEN``  only for ``/v1/catalog``
"""
from __future__ import annotations

import logging
import os

from .app import create_app
from .auth import from_env


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = create_app(auth=from_env())
    uvicorn.run(
        app,
        host=os.environ.get("ARB_HTTP_HOST", "127.0.0.1"),
        port=int(os.environ.get("ARB_HTTP_PORT", "8000")),
        log_level="warning",   # the audit logger is the request log; uvicorn's would duplicate it
    )


if __name__ == "__main__":
    main()
