"""Who is calling: a pluggable authenticator for the HTTP adapter.

A bank does not run on a shared secret. The caller is whoever the organisation's
identity provider says it is — PingFederate, PingOne, Keycloak, Entra: any OIDC
issuer — and this adapter only *verifies* that statement. It never issues anything.

The mechanism is the standard one and nothing else, which is what makes the IdP
swappable by configuration: a bearer token (RFC 6750) that is a JWT (RFC 7519),
signed with an asymmetric key the issuer publishes in its JWKS (RFC 7517), located
through OIDC discovery. Issuer and audience are checked, expiry is checked, and an
optional scope is required. HMAC algorithms are refused outright: a shared HMAC
secret would put the IdP's signing key on this server, which defeats the point.

Two authenticators implement one small protocol:

- ``JwtAuth``          — the real one. Picked when ``ARB_OIDC_ISSUER`` is set.
- ``StaticTokenAuth``  — a single pre-shared token, for a laptop or a demo with no
                         IdP at hand. Picked when only ``ARB_HTTP_TOKEN`` is set.

Setting both is refused as ambiguous; setting neither is refused because this
surface is never anonymous. ``domain/`` and ``application/`` know nothing of this
file: authentication is a transport concern and stays in the adapter.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

# Asymmetric only. Never HS*: see the module docstring.
ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384")


@dataclass(frozen=True, slots=True)
class Principal:
    """The verified caller, as the audit line names it."""
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)


class AuthError(Exception):
    """Refused. ``status`` is 401 (not authenticated) or 403 (authenticated, not allowed)."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Authenticator(Protocol):
    def authenticate(self, authorization: str) -> Principal:
        """Turn an ``Authorization`` header into a Principal, or raise AuthError."""
        ...


def _bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise AuthError(401, "bearer token required")
    return authorization[7:].strip()


# ── static: one pre-shared token, development only ────────────────────────────
class StaticTokenAuth:
    """Compare in constant time; name the caller by a hash prefix, never the token."""

    def __init__(self, token: str) -> None:
        if not token:
            raise RuntimeError("ARB_HTTP_TOKEN is empty")
        self._token = token.encode()

    def authenticate(self, authorization: str) -> Principal:
        given = _bearer(authorization).encode()
        if not hmac.compare_digest(given, self._token):
            raise AuthError(401, "invalid token")
        return Principal(subject="static:" + hashlib.sha256(given).hexdigest()[:12])


# ── OIDC: a JWT the identity provider signed ──────────────────────────────────
KeyResolver = Callable[[str], Any]
"""Given the raw token, return the public key that should have signed it."""


def _discover_jwks_url(issuer: str) -> str:
    """OIDC discovery: the only portable way to find the JWKS.

    PingOne serves it at ``{issuer}/jwks``, PingFederate at ``/pf/JWKS``, Keycloak at
    ``/protocol/openid-connect/certs``. Guessing the path would tie this file to one
    vendor; the discovery document is what every one of them publishes.
    """
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=5) as r:      # noqa: S310 - issuer is operator config
        doc: dict[str, Any] = json.load(r)
    if doc.get("issuer") != issuer:
        raise RuntimeError(
            f"discovery at {url} announces issuer {doc.get('issuer')!r}, expected {issuer!r}"
        )
    jwks: str = doc["jwks_uri"]
    return jwks


class JwtAuth:
    """Verify a JWT against the issuer's JWKS; require issuer, audience, expiry, scope.

    ``key_resolver`` is injectable so tests can hand in a key without a network;
    in production it is PyJWT's cached JWKS client, built lazily on the first call
    so that constructing the app does not talk to the IdP.
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        jwks_url: str | None = None,
        required_scope: str | None = None,
        key_resolver: KeyResolver | None = None,
        leeway_seconds: int = 30,
    ) -> None:
        if not issuer or not audience:
            raise RuntimeError("OIDC needs ARB_OIDC_ISSUER and ARB_OIDC_AUDIENCE")
        self.issuer = issuer
        self.audience = audience
        self.required_scope = required_scope
        self._jwks_url = jwks_url
        self._resolver = key_resolver
        self._leeway = leeway_seconds

    def _resolve_key(self, token: str) -> Any:
        if self._resolver is None:
            url = self._jwks_url or _discover_jwks_url(self.issuer)
            client = PyJWKClient(url, cache_keys=True, lifespan=600)
            self._resolver = lambda t: client.get_signing_key_from_jwt(t).key
        return self._resolver(token)

    def authenticate(self, authorization: str) -> Principal:
        token = _bearer(authorization)
        try:
            key = self._resolve_key(token)
            claims: dict[str, Any] = jwt.decode(
                token, key, algorithms=list(ALGORITHMS),
                issuer=self.issuer, audience=self.audience, leeway=self._leeway,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            # The reason goes to the caller in words, never the token or the key.
            raise AuthError(401, f"invalid token: {exc.__class__.__name__}") from exc
        # OAuth puts scopes in a space-separated ``scope``; Entra uses ``scp``.
        raw = claims.get("scope") or claims.get("scp") or ""
        scopes = frozenset(raw.split()) if isinstance(raw, str) else frozenset(raw)
        if self.required_scope and self.required_scope not in scopes:
            raise AuthError(403, f"scope {self.required_scope!r} required")
        # A machine caller (client_credentials) is best named by its client id —
        # Keycloak and Ping put it in ``azp`` / ``client_id`` — and a person by ``sub``.
        subject = str(claims.get("azp") or claims.get("client_id") or claims["sub"])
        return Principal(subject=subject, scopes=scopes)


# ── selection by configuration ────────────────────────────────────────────────
def from_env(env: dict[str, str] | None = None) -> Authenticator:
    """Exactly one mode. OIDC when an issuer is configured; static otherwise; never none."""
    e = os.environ if env is None else env
    issuer = e.get("ARB_OIDC_ISSUER", "")
    static = e.get("ARB_HTTP_TOKEN", "")
    if issuer and static:
        raise RuntimeError("ARB_OIDC_ISSUER and ARB_HTTP_TOKEN are both set; pick one")
    if issuer:
        return JwtAuth(
            issuer, e.get("ARB_OIDC_AUDIENCE", ""),
            jwks_url=e.get("ARB_OIDC_JWKS_URL") or None,
            required_scope=e.get("ARB_OIDC_SCOPE") or None,
        )
    if static:
        return StaticTokenAuth(static)
    raise RuntimeError(
        "no authentication configured: set ARB_OIDC_ISSUER (+ ARB_OIDC_AUDIENCE) "
        "for an identity provider, or ARB_HTTP_TOKEN for local development"
    )
