# arb-mcp — tool reference

What each tool does, what it takes, what it returns, what it refuses, and where
it sits in the flow. Written against the code in `src/arb_mcp/infra/mcp/stdio_server.py`
and the use cases it calls, not against the README. Where the two disagree,
`docs/AUDIT-2026-09-08.md` records it.

The server registers **five** tools. It has no LLM and calls none: the host (Kiro,
CI, a script) does the thinking, these tools supply the ground truth. Every tool
returns **one text payload**. It is JSON for every call except
`convert_model(to="structurizr")`, which returns the raw DSL.

## The one rule that shapes all of them

**Only deterministic validation may block a merge.** The verdict comes from a single
property, `Severity.blocking`, which is `severity is ERROR` and nothing else.
`build_model_tool` and `validate_model` compute it; `check_catalog` is informational
by design and never reaches it; `convert_model` and `describe_contract` have no verdict.

Two kinds of failure, and they are different things:

| kind | where it shows | meaning |
|---|---|---|
| **structural** — `{"error": "invalid_model", "detail": …}` | any tool that loads a source | the text could not become a schema-valid model at all: bad JSON, unknown type, a relation to a missing id. Nothing was linted. |
| **finding** — an entry in `findings[]` with a severity | `validate_model`, `build_model_tool` | the model is valid and a rule fired. Only `ERROR` blocks. |

A host must treat them differently: a structural failure means *fix the draft and
call again*; a finding means *the design has a defect the rules can name*.

---

## `describe_contract()`

**Purpose.** Return the contract a design must satisfy: the type spec (which node and
relation types exist, what contains what, what each type requires) and the normative
JSON Schema. A host calls it first so it drafts elements of the right shape instead
of guessing. It is the deterministic replacement for a generation prompt.

**Arguments.** None.

**Returns.**
```json
{ "spec": { "nodeTypes": {…}, "relationTypes": {…} }, "schema": { …draft 2020-12… } }
```
`spec` is the fixed C4 spec the server injects into every built model (see
`build_model_tool`). `schema` is the full normative schema — roughly 8 KB.

**Notes.** The spec returned is exactly what `build_model_tool` will enforce, so a
host that reads `spec.nodeTypes` and uses only those types cannot get a type error
later. Today that spec has four node types (`person`, `softwareSystem`, `container`,
`component`); `decision` and `deploymentNode` exist in the schema and in the lab spec
but not here — see audit M3.

---

## `build_model_tool(nodes, relations?, name?)`

**Purpose.** Assemble a canonical model from parts a host drafted, hold it to the
schema, lint it, and return the model together with its verdict. This is the
assembly step of the flow: epic → host drafts elements → this tool makes them a model.

**Arguments.**

| name | type | default | semantics |
|---|---|---|---|
| `nodes` | `list[object]` | required | the drafted elements, nested (`nodes` inside a node are its children). Each needs `id`, `type`, `name`; `description`, `technology`, `tags` as the type requires. |
| `relations` | `list[object]` | `[]` | `{from, to, description?, technology?, type?}`. A missing `type` is filled with the spec's first relation type (`uses` for C4). Endpoints are ids anywhere in the tree. |
| `name` | `string` | `"Design"` | model name. |

What the tool adds on its own: `version: "1.0"`, `scope: "system"`, the injected
`spec`, and `views: []`. **The host cannot supply a spec** — that is the point: the
agent cannot invent types.

**Returns, on success.**
```json
{ "ok": true,
  "model": { …the canonical model, ready for validate/convert/check_catalog… },
  "validation": { "may_merge": true, "blocking_count": 0, "findings": [ … ] } }
```
`validation` has the same shape as `validate_model`'s response.

**Returns, on a malformed draft.**
```json
{ "ok": false, "error": "invalid_model", "detail": "<exact schema failure>" }
```
`detail` is the jsonschema message — path and reason — which is the signal the host
uses to fix its next attempt. This is the only feedback loop in the system and it is
deterministic.

**Notes.** The returned `model` is the interchange form; pass it as `source` to the
other tools. Relations are copied before normalisation, so the caller's list is not
mutated. A node or relation whose `type` the injected spec does not declare is a
schema-valid model that fails the gate: `model.type.undeclared` /
`model.relation.type.undeclared`, both `ERROR`. That is the enforcement behind
"the agent cannot invent types" — until 2026-09-08 it was only a claim (audit H5).

---

## The same five over HTTP (`arb-mcp-http`)

`infra/http/app.py` is a FastAPI adapter over the same use cases — no logic of its
own, `domain/` never imports it, and FastAPI is an optional extra
(`pip install arb-mcp[http]`) so the core stays framework-free. It exists for two
callers stdio cannot serve: a CI pipeline, and a demo (`/docs` is the OpenAPI page).

| tool | route | body |
|---|---|---|
| `describe_contract` | `GET /v1/contract` | — |
| `build_model_tool` | `POST /v1/build` | `{nodes, relations?, name?}` |
| `validate_model` | `POST /v1/validate` | `{source, include_implied?}` |
| `convert_model` | `POST /v1/convert` | `{source, to?}` — `structurizr` returns `text/plain` |
| `check_catalog` | `POST /v1/catalog` | `{source}` |
| the MCP itself | `/mcp` | streamable HTTP from the SDK, same token |

Bodies and JSON responses are identical to the tools'. The only translation this
layer makes is the HTTP status, and it maps the two kinds of failure above:
**structural → 422**, unknown format → 400, catalog unreachable → 503, and a
finding is not a failure → **200 with `may_merge`** in the body.

**Auth.** Required on everything except `/health`, `/docs`, `/openapi.json`; a
middleware and not a dependency on purpose, so the mounted `/mcp` is covered too.
The guard delegates to an `Authenticator` (`infra/http/auth.py`) and there are two,
chosen by configuration — never both, never neither:

- **OIDC (production).** `ARB_OIDC_ISSUER` + `ARB_OIDC_AUDIENCE`, optional
  `ARB_OIDC_SCOPE` and `ARB_OIDC_JWKS_URL`. The token must be a JWT the identity
  provider signed — PingFederate, PingOne, Keycloak, Entra: any OIDC issuer — with
  an asymmetric algorithm (RS/PS/ES; HMAC is refused outright, so the IdP's key never
  lives here). Verified: signature against the issuer's JWKS found by OIDC
  discovery, `iss`, `aud`, `exp` (30 s leeway), and the scope if one is required.
  A missing scope is **403**, everything else **401**; the detail names the reason
  and never echoes the token. The audit `caller` is the client id (`azp` /
  `client_id`) for a machine caller and `sub` for a person. Proven end-to-end
  against a live Keycloak with a `client_credentials` token (PS256, `aud` via
  audience mapper, scope via a default client scope).
- **Static (development).** `ARB_HTTP_TOKEN`, one pre-shared token compared in
  constant time; `caller` is a hash prefix of it.

This adapter only *verifies*; it issues nothing. Swapping the IdP is configuration.

**Audit.** One JSON line per request on the `arb_mcp.audit` logger — method, path,
status, milliseconds, and `caller` (a 12-hex prefix of the token's SHA-256, enough
to tell two tokens apart; the token itself is never logged).

**Run.** `ARB_HTTP_TOKEN=… arb-mcp-http` (binds `127.0.0.1:8000`; set
`ARB_HTTP_HOST=0.0.0.0` only behind TLS). Or the image: `Dockerfile` is
multi-stage, runs as a non-root user, and has a `/health` HEALTHCHECK.

---

## `validate_model(source, include_implied=false)`

**Purpose.** The merge gate. Load a design from any accepted surface and report
whether it may merge.

**Arguments.**

| name | type | default | semantics |
|---|---|---|---|
| `source` | `string` | required | a design as text. Format is **detected**: starts with `{` → canonical JSON; starts with `workspace` (comments allowed before it) → Structurizr DSL; otherwise `.arch`. Detection is anchored at the start of the text, so a stray `workspace` inside a description cannot hijack it. |
| `include_implied` | `bool` | `false` | also derive the implied relations (Structurizr's `CreateImpliedRelationshipsUnlessAnyRelationshipExists`, persons never counting as parent or child) and lint those too. With `true`, rule counts match the official CLI, which inspects derived relations; with `false`, only what the author wrote is judged. |

**Returns.**
```json
{ "may_merge": false,
  "blocking_count": 2,
  "findings": [
    { "severity": "ERROR", "rule": "model.relation.technology",
      "message": "The relationship between … is missing a technology.", "blocking": true },
    { "severity": "WARNING", "rule": "model.softwareSystem.documentation",
      "message": "…", "blocking": false } ] }
```
`may_merge` is `true` iff `blocking_count` is `0`. `findings` is the full list, all
severities. Rules are namespaced (`model.<type>.<aspect>`); the four that the
official Structurizr CLI also fires are verified identical against it
(`tools/test_cross_inspections`).

**Returns, when the source is not a model.**
```json
{ "may_merge": false, "error": "invalid_model", "detail": "…" }
```
Note `may_merge: false` is set here too, so a host that only reads that key still
gets a safe answer — but it should read `error` to tell this from a lint failure.

**Notes.** The facade adds three rules of its own on top of the ported engine —
`model.empty`, `model.id.duplicate`, `model.relation.endpoint` — because a duplicate
id silently overwrites a diagram cell and a dangling endpoint cannot be drawn. All
three are `ERROR`. A finding carries its subject inside `message`; there is no
separate `subject` field yet (audit M7).

---

## `convert_model(source, to="drawio")`

**Purpose.** Export a design to another surface. Every surface is an exporter over
the same model the linter validated, so a diagram and its verdict cannot drift.

**Arguments.**

| name | type | default | semantics |
|---|---|---|---|
| `source` | `string` | required | any accepted surface; detected as above. |
| `to` | `string` | `"drawio"` | target. Advertised: `drawio`, `structurizr`. Also accepted, unadvertised: `arch` (audit M5). |

**Returns, `to="drawio"`.** JSON with the C4 views as **separate diagrams**, one
standalone `<mxfile>` each — one C1 (System Context), one C2 per software system,
one C3 per container. Never one file with tabs: a bank stores, reviews and versions
each level on its own.
```json
{ "views": [
    { "level": "C1", "scope": "landscape", "name": "System Context", "xml": "<mxfile …>" },
    { "level": "C2", "scope": "billing",   "name": "Billing — Containers", "xml": "…" },
    { "level": "C3", "scope": "api",       "name": "API — Components", "xml": "…" } ] }
```
Every cell is a native C4 `<object>` with `c4Name`/`c4Type`/`c4Description`
placeholders and the style strings lifted verbatim from drawio's `mxgraph.c4`
stencil, so the file opens as editable C4 shapes in drawio's own panel. Relation
endpoints are lifted to the element visible at that level.

**Returns, `to="structurizr"`.** The raw Structurizr DSL as text — not JSON. Covers
the C4 surface (person, softwareSystem, container, component), relations and the
C1/C2/C3 views. Types Structurizr has no inline syntax for — a `decision` is an ADR
there, not an element — are **skipped**; the caller keeps them in the canonical model.
This direction is lossy for exactly those.

**Returns, unknown target.**
```json
{ "ok": false, "error": "unknown format 'png'; known: drawio, structurizr", "formats": ["drawio", "structurizr"] }
```
And `{"ok": false, "error": "invalid_model", …}` if the source does not load.

**Notes.** Sizes and gaps in the drawio output are currently literals inside
`domain/drawio.py` (210×110, boundary 320) and differ from drawio's palette
(240×120); they will move to a render profile (audit H3/H4). Layout is the
exporter's own column placement; the auto-layout of drawio was tried and rejected.

---

## `check_catalog(source)`

**Purpose.** Reconcile a design against the organisation's architecture catalog —
SAP LeanIX, the source of truth. For every catalog-relevant element, say whether it
already exists there (with its catalog id) or is new and must be registered. In the
flow it goes **before** creating anything, so existing components are reused instead
of duplicated.

**Arguments.** `source` — any accepted surface.

**Environment.** `LEANIX_BASE_URL`, `LEANIX_API_TOKEN`. Auth is OAuth2 client
credentials at `/services/mtm/v1/oauth2/token` with `apitoken:<token>`; lookups are
GraphQL `allFactSheets` at `/services/pathfinder/v1/graphql`, filtered by fact-sheet
type and full-text search, then matched by **exact name** (fuzzy matching produced
false "known"s in audit). A `401` retries the token once.

**What it checks.** Only `softwareSystem`, `container`, `component`. A `person` or a
`decision` is not a catalog fact sheet and is skipped.

**Returns.**
```json
{ "ok": true, "checked": 7,
  "known":   [ { "id": "api", "name": "Billing API", "type": "container",
                 "catalog_id": "f1a2…", "catalog_name": "Billing API" } ],
  "unknown": [ { "id": "scanner", "name": "Isolated scanner", "type": "container" } ],
  "coverage": 0.857 }
```
`coverage` is `known / checked`, `1.0` when nothing was checkable.

**Errors.** `{"ok": false, "error": "invalid_model", …}` if the source does not
load; `{"ok": false, "error": "catalog_unavailable", "detail": …}` when the
environment is missing or LeanIX cannot be reached (network errors are caught and
reported, never raised into the host).

**Notes.** **Informational only. It never blocks a merge** — the catalog can be out
of date, and a reconciliation must not veto a design. Live LeanIX has not been
exercised yet (no credentials); the adapter is tested with a double.

---

## How a host drives them

```
1. describe_contract()                       → learn the types and the schema
2. <host drafts nodes/relations from the epic>
3. build_model_tool(nodes, relations)        → {ok, model, validation}   ← fix and repeat on ok:false
4. check_catalog(model)                      → reuse what LeanIX already has   (informational)
5. validate_model(model, include_implied=true)  → may_merge                   (the gate)
6. convert_model(model, "drawio")            → C1 / C2… / C3… for review
   convert_model(model, "structurizr")       → the DSL the repo already versions
```
Steps 3 and 5 are the only ones that can say no. Nothing in step 2 — the
probabilistic part — is on the path to the verdict.

---

## Lab tools not yet promoted (geometry layer)

Built on 2026-09-08 in `~/lab/2026-08-20-dsl-arquitectura/spec/tools/`, on the same
engine this repo vendors. They are the next thing to promote, once the vendored copy
is refreshed (audit H1). Listed so nobody rebuilds them.

| tool | what it does | belongs to |
|---|---|---|
| `resolve_layout.py` | turns `rank`/`order` cells into rectangles — pure arithmetic, no solver. A node the view returns and the layout omits is placed after the last rank and marked `derived`. | domain (standard) |
| `ordinal_inspections.py` | the layout rules that never touch a pixel: `duplicate-cell`, `rank-gap`, `backward-edge`, `edge-crossing` counted the Sugiyama way (endpoints in opposite order between adjacent ranks). Their fix is always "change a rank/order". | domain (standard) |
| `render_inspections.py` | render QA against a profile: containment, sibling overlap, edge through a foreign node, label on a route; plus corridor/rhythm/frame-hugging for orthogonal routing. Their fix is always "move N units". May report a bad drawing, may never propose a model change. | exporter |
| `layout_geometry.py` | the pure primitives (rects, segments, collinear overlap, clearance) the two above share. Ported from tt-a1i/archify (MIT). | exporter |
| `to_drawio.py` | drawio exporter driven by cells, geometry **relative to the parent cell**, sizes from `examples/c4.render.json`; verified by opening the file in drawio. | exporter — to merge with `domain/drawio.py` (audit H4) |
| `check_drawio.py` | reads a `.drawio` the way drawio does: parent missing or declared after the child, child geometry outside its parent, dangling edge endpoint, duplicate id. | exporter QA |
| `examples/c4.render.json` | the render profile: per-type size, shape, colours, grid gaps. **The model never references it**; the caller picks it. | render profile |

Measured reason the layer exists: across dagre, elk and Graphviz on the same graph,
vertical **order** survives (0–1.1 % of pairs invert) while coordinates do not (only
22–69 % of nodes keep their nearest neighbour). The standard therefore fixes the
order and leaves the pixels to the exporter.
