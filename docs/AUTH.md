# Authentication — the HTTP adapter

Who may call `/v1/*` and `/mcp`, how that is decided, and how it is configured.
Everything here lives in `src/arb_mcp/infra/http/auth.py` and the guard in
`app.py`; `domain/` and `application/` know nothing of it. The adapter only
**verifies** credentials. It never issues one.

## Modes

There are two, and exactly one is active. There is no silent default: the mode is
whatever the environment configures, and configuring both or neither refuses to
start.

| mode | class | for | selected when |
|---|---|---|---|
| **OIDC / JWT** | `JwtAuth` | production — any OIDC identity provider: PingFederate, PingOne, Keycloak, Entra ID | `ARB_OIDC_ISSUER` is set |
| **Static token** | `StaticTokenAuth` | a laptop or a demo with no IdP at hand | only `ARB_HTTP_TOKEN` is set |

### OIDC / JWT

The bearer must be a JWT the identity provider signed. Verification, in order:

1. **Signature**, against the issuer's JWKS (RFC 7517), located through OIDC
   discovery (`{issuer}/.well-known/openid-configuration`) unless `ARB_OIDC_JWKS_URL`
   pins it. Discovery is refused if the document names a different issuer.
   Keys are cached (PyJWT's `PyJWKClient`, 10 min) and fetched lazily on the first
   call, so starting the app does not talk to the IdP.
2. **Algorithm allow-list**: RS256/384/512, PS256/384/512, ES256/384. **HMAC is refused
   outright** — a symmetric secret would put the IdP's signing key on this server and
   opens the classic key-confusion forgery.
3. `iss` must equal `ARB_OIDC_ISSUER`; `aud` must contain `ARB_OIDC_AUDIENCE`; `exp`
   is required, with 30 s of leeway.
4. If `ARB_OIDC_SCOPE` is set, the token must carry it — in `scope` (space-separated,
   OAuth; Ping and Keycloak) or `scp` (Entra ID).

Works for machines and people alike: a `client_credentials` token from a CI
pipeline and an authorization-code token from a person are both JWTs from the same
issuer. The audit line names a machine by its client id (`azp` / `client_id`) and a
person by `sub`.

### Static token

One pre-shared token compared in constant time. The audit line names the caller by
a 12-hex prefix of the token's SHA-256, never the token. Development only.

## Configuration (environment only)

No flags, no config file: a container and a laptop start the same way.

```
# ── OIDC (production) ─────────────────────────────────────────────────────
ARB_OIDC_ISSUER=https://auth.example.com/realms/arb   # required; activates the mode.
                                                       # Must equal the token's `iss`
                                                       # and the discovery document's.
ARB_OIDC_AUDIENCE=arb-mcp                              # required with the issuer
ARB_OIDC_SCOPE=arb:validate                            # optional; missing → 403
ARB_OIDC_JWKS_URL=http://idp-internal:8080/.../certs   # optional; skips discovery,
                                                       # for an internal JWKS route

# ── Static (development only) ─────────────────────────────────────────────
ARB_HTTP_TOKEN=…                                       # refused if an issuer is set too

# ── Server ────────────────────────────────────────────────────────────────
ARB_HTTP_HOST=127.0.0.1                                # 0.0.0.0 only behind TLS
ARB_HTTP_PORT=8000
LEANIX_BASE_URL / LEANIX_API_TOKEN                     # only for /v1/catalog
```

Pass them with `--env-file` (mode 600) so no secret ever sits on a command line,
in shell history or in `ps`. Nothing of this goes in the repository.

## What the caller gets

| situation | status | body |
|---|---|---|
| open path (`/health`, `/docs`, `/openapi.json`, `/redoc`) | 200 | — no credential needed |
| no `Authorization`, not a bearer, bad signature, wrong `iss`/`aud`, expired | **401** | `{"error":"unauthorized","detail":"<reason>"}` |
| valid token, required scope missing | **403** | `{"error":"forbidden","detail":"scope 'arb:validate' required"}` |

`detail` names the reason in words (`invalid token: ExpiredSignatureError`) and
never echoes the token or the key. The guard is a middleware, not a FastAPI
dependency, so the mounted `/mcp` transport is covered by the same rule.

## The audit line

One JSON line per request on the `arb_mcp.audit` logger:

```
{"method":"GET","path":"/v1/contract","status":200,"ms":22.0,"caller":"arb-mcp-ci"}
{"method":"GET","path":"/v1/contract","status":401,"ms":0.2,"caller":"rejected:416bccbf83bb"}
{"method":"GET","path":"/v1/contract","status":401,"ms":0.0,"caller":"anonymous"}
```

`caller` is, in order: the verified subject; `rejected:<hash prefix of what was
presented>` when a credential was offered and refused — an auditor must tell a
failed attempt from a probe —; `anonymous` when nothing was presented. The
credential itself is never written.

## Setting up an identity provider

What the IdP must do, in any vendor's words: issue a JWT with an asymmetric
signature, with `iss` = the issuer URL, `aud` containing the audience, and the
scope in `scope` or `scp`. The recipe below is what was done on a live Keycloak
and is the same shape in PingFederate (OAuth client + access token manager +
scope) and PingOne (application + resource + scope).

**Keycloak, machine-to-machine (`client_credentials`):**

1. Confidential client `arb-mcp-ci`, *service accounts enabled*, standard flow and
   direct grants off.
2. **Audience**: a protocol mapper of type `oidc-audience-mapper` with
   `included.custom.audience = arb-mcp`, added to the access token. Without it the
   token's `aud` is `account` and verification fails on audience.
3. **Scope**: a client scope named `arb:validate` with `include.in.token.scope = true`,
   assigned as a **default client scope of the client**. Until both are done the
   token carries only `email profile` and verification fails with 403.
4. Mint: `POST {issuer}/protocol/openid-connect/token` with
   `grant_type=client_credentials&client_id=…&client_secret=…`.

Two traps, both cost a round trip: `kcadm get client-scopes -q name=X` does **not**
filter (list `--fields id,name` and grep); and when the adapter runs in a container,
`127.0.0.1` is the container's loopback — put the container on the IdP's network and
use its service name for `ARB_OIDC_JWKS_URL`, while `ARB_OIDC_ISSUER` stays the public
URL, because that is what the token carries in `iss`.

## Verified how

- **Without network**, 17 tests over an RSA key generated per session and injected as
  the key resolver: expiry, audience, issuer, foreign signature, missing scope → 403,
  `scp` claim, HS256 forgery with the right secret, discovery naming another issuer,
  a non-bearer header, and mode selection (both / neither / issuer without audience).
- **End to end**, against a live Keycloak: a PS256 `client_credentials` token → 200
  with `caller: arb-mcp-ci`; the previous static token → 401; a tampered token →
  401 as `rejected:…`; no token → 401 as `anonymous`; `/docs` → 200.

## Not implemented (say so before promising it)

- **Opaque-token introspection** (RFC 7662) — for IdPs that do not issue JWTs, or
  for immediate revocation.
- **mTLS** client certificates — often required CI-to-CI.
- **DPoP / sender-constrained tokens** (RFC 9449) — so a stolen token is useless
  from another host.
- **Per-tool authorization** — today one scope gates everything; splitting
  `arb:validate` / `arb:convert` / `arb:catalog` is a small change in the same place.

Each of these is one more `Authenticator` (or a check inside the existing one);
nothing outside `infra/http/` moves.
