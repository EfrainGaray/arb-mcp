## v0.1.0 (2026-09-08)

### Feat

- **release**: reproducible build, SBOM and image from any CI
- **domain**: typed view queries, evaluated; two view rules in the gate
- **drawio**: one exporter driven by a render profile and the ordinal layout
- **infra**: OIDC authentication for the HTTP adapter — the caller is whoever the IdP says
- **infra**: HTTP adapter (FastAPI) over the same use cases, with token and audit; Dockerfile
- **domain**: recursive flat view for arbitrary-depth notations (deployment)
- reconcile a design against the LeanIX catalog (source of truth)
- **domain**: Structurizr DSL exporter with C1/C2/C3 views, round-trip tested
- **domain**: emit C4 as separate C1/C2/C3 drawio views, never tabbed
- **application**: convert use case and MCP tools for generate and convert (Structurizr DSL to drawio)
- **domain**: drawio C4 exporter using verbatim mxgraph.c4 stencil styles
- **infra**: canonical C4 spec resource and OpenAI-compatible LLM adapter
- **infra**: stdio MCP adapter exposing validate_model
- **application**: ports and the validate-model use case
- **domain**: typed facade over the engine (findings, loading, linter)
- **domain**: vendor the bit-for-bit DSL engine as an internal dependency

### Fix

- **domain**: dataclass mapping defaults as factories for Python 3.11
- **infra**: audit names a refused credential apart from an anonymous probe
- **infra**: uniform error shape for check_catalog (error/detail codes)
- **domain**: bound model nesting depth so deep input fails as ModelError
- **infra**: LeanIX adapter handles network errors, exact-name match, token retry
- **domain**: Structurizr skips non-C4 relation endpoints and folds newlines
- **domain**: C2/C3 keep relations to the focus element; flat lifts deep endpoints
- **application**: copy caller relations before normalizing; expose C4_SPEC
- **domain**: fold double quotes to apostrophes in Structurizr export
- **domain**: guard drawio against dangling endpoints and namespace edge ids
- **domain**: block dangling relation endpoints and duplicate ids
- **domain**: block a schema-valid model that declares no elements
- **domain**: unpack from_structurizr tuple and anchor format detection

### Refactor

- **domain**: rewrite the vendored engine over the typed model
- **domain**: typed canonical model; drop the .arch text surface
- reach the engine only through the facade; drop dead code
- **infra**: reach schema and spec through the public facade, not engine internals
- remove the LLM from the MCP; Kiro drives deterministic tools
- **application**: validate and generate over the canonical model
