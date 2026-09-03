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

## The tools (how you use it)

The server exposes three MCP tools. A client (Kiro, Claude, any MCP host) calls
them by name; every task is one call.

| I want to… | Tool | Call |
|---|---|---|
| Create a design from a prompt / epic / file | `generate_model` | `generate_model(description, stories?, name?)` → `{model, validation}` |
| Validate a design (the merge gate) | `validate_model` | `validate_model(source)` → `{may_merge, blocking_count, findings}` |
| Get the `.arch` DSL of a design | `convert_model` | `convert_model(source, to="arch")` → DSL text |
| Get the Structurizr DSL | `convert_model` | `convert_model(source, to="structurizr")` → DSL text |
| Get the drawio C4 diagrams | `convert_model` | `convert_model(source, to="drawio")` → `{views:[{level,scope,name,xml}]}` |

`source` is a design in any accepted surface — `.arch`, canonical schema JSON,
or Structurizr DSL — the format is detected. Only `validate_model` decides a
merge; `generate_model` is non-blocking and returns the same validation report
so you see what the draft still breaks. drawio always comes back as **separate
C4 views** (one C1, one C2 per system, one C3 per container), never tabs.

Typical chain: `generate_model` → read `validation` → fix → `convert_model
to="drawio"` for the diagrams and `to="structurizr"` for the repo DSL.

### Run it

    # stdio (local, for an editor / Kiro power)
    arb-mcp
    # or: python -m arb_mcp.infra.mcp.stdio_server

Register it as a Kiro power in `~/.kiro/settings/mcp.json`. Generation needs
`ARB_LLM_BASE_URL` and `ARB_LLM_MODEL` in the environment (any OpenAI-compatible
endpoint — a local llama-server included).
