"""OIDC authentication for the HTTP adapter, verified without any network.

An RSA key pair is generated per test session and injected as the key resolver, so
these tests prove the verification logic — issuer, audience, expiry, signature,
scope, algorithm — against tokens we mint ourselves. What they cannot prove is the
JWKS fetch from a live issuer; that is exercised against a real Keycloak in the
deployment check, not here.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from arb_mcp.infra.http import auth as auth_mod
from arb_mcp.infra.http.app import create_app
from arb_mcp.infra.http.auth import AuthError, JwtAuth, Principal, StaticTokenAuth, from_env

ISS = "https://idp.example.test/realms/arb"
AUD = "arb-mcp"


@pytest.fixture(scope="session")
def keys() -> tuple[Any, Any]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture(scope="session")
def other_key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def mint(priv: Any, **over: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISS,
        "aud": AUD,
        "sub": "3f1c-service-account",
        "azp": "ci-pipeline",
        "iat": now,
        "exp": now + 300,
        "scope": "arb:validate arb:convert",
    }
    claims.update(over)
    for k in [k for k, v in claims.items() if v is None]:
        del claims[k]
    alg = str(over.pop("_alg", "RS256"))
    return jwt.encode(claims, priv, algorithm=alg, headers={"kid": "test-key"})


@pytest.fixture
def jwt_auth(keys: tuple[Any, Any]) -> JwtAuth:
    _, pub = keys
    return JwtAuth(ISS, AUD, required_scope="arb:validate", key_resolver=lambda _t: pub)


@pytest.fixture
def client(jwt_auth: JwtAuth) -> TestClient:
    return TestClient(create_app(auth=jwt_auth))


# ── the verifier itself ───────────────────────────────────────────────────────
def test_valid_token_names_the_client_not_the_uuid(
    keys: tuple[Any, Any],
    jwt_auth: JwtAuth,
) -> None:
    p = jwt_auth.authenticate("Bearer " + mint(keys[0]))
    assert p == Principal(subject="ci-pipeline", scopes=frozenset({"arb:validate", "arb:convert"}))


def test_person_token_falls_back_to_sub(keys: tuple[Any, Any], jwt_auth: JwtAuth) -> None:
    p = jwt_auth.authenticate("Bearer " + mint(keys[0], azp=None, sub="efrain"))
    assert p.subject == "efrain"


@pytest.mark.parametrize(
    ("bad", "status"),
    [
        ({"exp": int(time.time()) - 3600}, 401),  # expired
        ({"aud": "someone-else"}, 401),  # wrong audience
        ({"iss": "https://evil.example.test"}, 401),  # wrong issuer
        ({"scope": "arb:convert"}, 403),  # authenticated, scope missing
        ({"scope": None}, 403),  # no scope claim at all
    ],
)
def test_refusals(
    keys: tuple[Any, Any],
    jwt_auth: JwtAuth,
    bad: dict[str, Any],
    status: int,
) -> None:
    with pytest.raises(AuthError) as e:
        jwt_auth.authenticate("Bearer " + mint(keys[0], **bad))
    assert e.value.status == status


def test_wrong_signing_key_is_401(other_key: Any, jwt_auth: JwtAuth) -> None:
    with pytest.raises(AuthError) as e:
        jwt_auth.authenticate("Bearer " + mint(other_key))
    assert e.value.status == 401


def test_hmac_is_refused_even_when_the_resolver_hands_back_the_secret() -> None:
    """HS* is outside the allow-list, full stop.

    Accepting a symmetric algorithm would mean the IdP's signing secret lives on
    this server, and — the classic confusion attack — a token signed with the
    *public* key as an HMAC secret could pass. PyJWT itself refuses to use a PEM as
    an HMAC secret, so the forgery here uses a plain string; the point under test is
    that even a resolver that returns the right symmetric secret is not enough."""
    now = int(time.time())
    forged = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "x", "exp": now + 300, "scope": "arb:validate"},
        "shared-secret",
        algorithm="HS256",
    )
    a = JwtAuth(ISS, AUD, key_resolver=lambda _t: "shared-secret")
    with pytest.raises(AuthError) as e:
        a.authenticate("Bearer " + forged)
    assert e.value.status == 401


def test_scp_claim_is_accepted_as_scopes(keys: tuple[Any, Any]) -> None:
    """Entra ID puts scopes in ``scp``; Ping and Keycloak in ``scope``."""
    a = JwtAuth(ISS, AUD, required_scope="arb:validate", key_resolver=lambda _t: keys[1])
    p = a.authenticate("Bearer " + mint(keys[0], scope=None, scp="arb:validate"))
    assert "arb:validate" in p.scopes


def test_not_a_bearer_header_is_401(jwt_auth: JwtAuth) -> None:
    with pytest.raises(AuthError) as e:
        jwt_auth.authenticate("Basic dXNlcjpwYXNz")
    assert e.value.status == 401


# ── wired into the adapter ────────────────────────────────────────────────────
def test_adapter_accepts_idp_token_and_audits_the_client_id(
    client: TestClient,
    keys: tuple[Any, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="arb_mcp.audit"):
        r = client.get("/v1/contract", headers={"Authorization": "Bearer " + mint(keys[0])})
    assert r.status_code == 200
    entry = json.loads([x.getMessage() for x in caplog.records if x.name == "arb_mcp.audit"][-1])
    assert entry["caller"] == "ci-pipeline"


def test_adapter_returns_403_not_401_when_only_the_scope_is_missing(
    client: TestClient,
    keys: tuple[Any, Any],
) -> None:
    tok = mint(keys[0], scope="other")
    r = client.get("/v1/contract", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403 and r.json()["error"] == "forbidden"


def test_adapter_401_body_never_echoes_the_token(client: TestClient, keys: tuple[Any, Any]) -> None:
    tok = mint(keys[0], aud="nope")
    r = client.get("/v1/contract", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 401 and tok not in r.text


# ── mode selection ────────────────────────────────────────────────────────────
def test_from_env_picks_oidc_when_issuer_is_set() -> None:
    a = from_env(
        {
            "ARB_OIDC_ISSUER": ISS,
            "ARB_OIDC_AUDIENCE": AUD,
            "ARB_OIDC_SCOPE": "arb:validate",
        }
    )
    assert isinstance(a, JwtAuth) and a.required_scope == "arb:validate"


def test_from_env_picks_static_when_only_token_is_set() -> None:
    assert isinstance(from_env({"ARB_HTTP_TOKEN": "t"}), StaticTokenAuth)


def test_from_env_refuses_both_and_none() -> None:
    with pytest.raises(RuntimeError):
        from_env({"ARB_OIDC_ISSUER": ISS, "ARB_OIDC_AUDIENCE": AUD, "ARB_HTTP_TOKEN": "t"})
    with pytest.raises(RuntimeError):
        from_env({})


def test_oidc_without_audience_is_refused() -> None:
    with pytest.raises(RuntimeError):
        from_env({"ARB_OIDC_ISSUER": ISS})


def test_discovery_rejects_a_document_for_another_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A discovery document that names a different issuer is an attack or a
    misconfiguration; either way the JWKS it points at must not be trusted."""

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"issuer": "https://other.test", "jwks_uri": "https://other.test/jwks"}
            ).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError):
        auth_mod._discover_jwks_url(ISS)
