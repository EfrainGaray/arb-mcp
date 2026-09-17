# arb-mcp

Architecture Review Board MCP. A Python MCP server that validates, converts and
queries C4/architecture designs. It is the engine of a Kiro Power
(POWER.md + this server + hooks).

The JSON Schema is normative and schema-valid JSON is the canonical model and the interchange form. Structurizr DSL is an accepted input surface and what it cannot carry is reported as lost, never dropped silently. drawio, Structurizr DSL and Mermaid are exports over the validated model, with round-trip guaranteed for what each notation can express.

Deterministic validation is the only thing that can block a merge. Generation
from an epic is probabilistic and always non-blocking, kept out of the
validation path by construction.

## Layers (clean)

- `domain/` — the typed canonical model (`model.py`: frozen `Model`, `Node`,
  `Relation`, `Spec`, mirrors of the normative JSON Schema), the loader that
  holds any input to the schema, the linter, and the exporters (drawio,
  Structurizr), the spec-driven `inspections`, the `implied` relations
  transformation and the Structurizr DSL parser — all typed, all under the
  same ruff/mypy/coverage gates. Nothing is vendored or exempt any more.
- `application/` — use cases and ports.
- `infra/` — transport adapters: stdio for the architect, HTTP (FastAPI) for CI and demos, authenticated against the organisation's identity provider (OIDC/JWT) or a static token for local work.

## Tests, three layers

- `tests/features/*.feature` — the merge gate as Gherkin scenarios the
  architecture review board can read and sign off; pytest-bdd runs them
  against the real linter. Only the deterministic gate lives here.
- `tests/test_properties.py` — hypothesis invariants over generated models:
  determinism, totality, round-trip, well-formed exports.
- plain pytest for everything else; `engine_golden.json` pins the verdicts
  measured against the official Structurizr CLI.

## Release (reproducible, host-agnostic)

    make release        # wheel + sdist, CycloneDX SBOM, SHA256SUMS, OCI image
    make push REGISTRY=registry.example/arch/arb-mcp

Every target lives in the Makefile; `.github/workflows/release.yml` and the
`release` job in `.gitlab-ci.yml` only run it on a `v*` tag and keep `dist/`.
The base image is pinned by digest, the runtime installs the wheel that was
just built (not the source tree), and the image carries OCI labels with the
version and commit. Version has one source: `pyproject.toml`, read at runtime
through `importlib.metadata` and reported by `/health`.

## Version and changelog

    make changelog      # what the next release would say
    make bump           # version from the commits, CHANGELOG.md, tag v*
    git push --follow-tags

commitizen reads the conventional commits the commit-msg hook already enforces:
`fix` bumps patch, `feat` minor, a `BREAKING CHANGE` footer major. Nobody edits
the version or the changelog by hand.

## Develop

    python -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'
    pytest && ruff check src/ && mypy

## The tools (how Kiro uses it)

**This MCP has no LLM and calls none.** Kiro does the thinking — it reads the
epic, drafts the C4 elements — and drives these deterministic tools. Five tools:

| Kiro wants to… | Tool | Call |
|---|---|---|
| Know what shape to draft | `describe_contract` | `describe_contract()` -> `{spec, schema}` |
| Turn its draft into a validated model | `build_model_tool` | `build_model_tool(nodes, relations?, name?)` -> `{ok, model, validation}` |
| Validate a design (the merge gate) | `validate_model` | `validate_model(source)` -> `{may_merge, blocking_count, findings}` |
| Get the diagrams / DSL | `convert_model` | `convert_model(source, to)` -> drawio views / Structurizr DSL |
| Reconcile against the catalog (source of truth) | `check_catalog` | `check_catalog(source)` -> known / unknown components (needs LeanIX env) |

Typical loop, all inside Kiro:

1. `describe_contract()` — Kiro learns the allowed C4 types and the schema.
2. Kiro drafts `nodes`/`relations` from the epic (its own reasoning).
3. `build_model_tool(nodes, relations)` — the MCP injects the fixed spec, holds
   it to the schema, and returns the model plus its validation report. A
   malformed draft comes back with the exact schema failure, which Kiro fixes.
4. `convert_model(model, to="drawio")` for the separate C1/C2/C3 diagrams and
   `to="structurizr"` for the repo DSL.

`source` is any accepted surface — canonical schema JSON or Structurizr DSL;
the format is detected. Only `validate_model` decides a merge. drawio always
comes back as **separate C4 views** (one C1, one C2 per system, one C3 per
container), never tabs.

### Run it

    arb-mcp                                   # stdio
    # or: python -m arb_mcp.infra.mcp.stdio_server

Register it as a Kiro power in `~/.kiro/settings/mcp.json`. No LLM environment is
needed — the host provides the intelligence.

## API reference

Every tool call and response, captured from the running server: [docs/API.md](docs/API.md). Tool reference: [docs/TOOLS.md](docs/TOOLS.md). Authentication modes and configuration: [docs/AUTH.md](docs/AUTH.md). Regenerate with `python docs/gen_api.py` (from an active venv).

## The same canonical model, another notation

UML use cases from the same schema, exported to DSL and to drawio — a worked example with real engine output: [docs/EJEMPLO-UML.md](docs/EJEMPLO-UML.md).
