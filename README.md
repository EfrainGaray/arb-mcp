# arb-mcp

Architecture Review Board MCP. A Python MCP server that validates, converts and
queries C4/architecture designs, and drafts them from epics. It is the engine of
a Kiro Power (POWER.md + this server + hooks).

Deterministic validation is the only thing that can block a merge. Generation
from an epic is probabilistic and always non-blocking, kept out of the
validation path by construction.

## Layers (clean)

- `domain/` — the vendored, bit-for-bit engine (schema, grammar, inspections,
  implied relations) behind a typed facade (`findings`, `loading`, `linter`).
- `application/` — use cases and ports.
- `infra/` — transport adapters (stdio today; HTTP/SSE with auth next) and the
  outward ports (Jira, LLM, drawio).

## Develop

    python -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'
    pytest && ruff check src/ && mypy

## The tools (how Kiro uses it)

**This MCP has no LLM and calls none.** Kiro does the thinking — it reads the
epic, drafts the C4 elements — and drives these deterministic tools. Four tools:

| Kiro wants to… | Tool | Call |
|---|---|---|
| Know what shape to draft | `describe_contract` | `describe_contract()` -> `{spec, schema}` |
| Turn its draft into a validated model | `build_model_tool` | `build_model_tool(nodes, relations?, name?)` -> `{ok, model, validation}` |
| Validate a design (the merge gate) | `validate_model` | `validate_model(source)` -> `{may_merge, blocking_count, findings}` |
| Get the diagrams / DSLs | `convert_model` | `convert_model(source, to)` -> drawio views / `.arch` / Structurizr DSL |

Typical loop, all inside Kiro:

1. `describe_contract()` — Kiro learns the allowed C4 types and the schema.
2. Kiro drafts `nodes`/`relations` from the epic (its own reasoning).
3. `build_model_tool(nodes, relations)` — the MCP injects the fixed spec, holds
   it to the schema, and returns the model plus its validation report. A
   malformed draft comes back with the exact schema failure, which Kiro fixes.
4. `convert_model(model, to="drawio")` for the separate C1/C2/C3 diagrams and
   `to="structurizr"` for the repo DSL.

`source` is any accepted surface — `.arch`, canonical schema JSON, or Structurizr
DSL; the format is detected. Only `validate_model` decides a merge. drawio always
comes back as **separate C4 views** (one C1, one C2 per system, one C3 per
container), never tabs.

### Run it

    arb-mcp                                   # stdio
    # or: python -m arb_mcp.infra.mcp.stdio_server

Register it as a Kiro power in `~/.kiro/settings/mcp.json`. No LLM environment is
needed — the host provides the intelligence.
