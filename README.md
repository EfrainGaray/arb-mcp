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
