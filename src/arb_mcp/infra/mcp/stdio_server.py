"""stdio MCP adapter: exposes the use cases as MCP tools over stdio.

This is the local surface — the architect's Kiro Power talks to this process
directly, no network. The HTTP/SSE adapter (auth + audit log, for CI) shares
the exact same use cases and adds nothing to the validation logic.

First tool wired: ``validate_model``. The others (convert, query, generate)
follow the same pattern — thin adapters over ``application`` — and are added as
their use cases land.
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from ...application.validate_model import validate_source
from ...domain.loading import ModelError

mcp = MCPServer("arb-mcp")


@mcp.tool()
def validate_model(source: str, include_implied: bool = False) -> str:
    """Validate an architecture design and report whether it may merge.

    ``source`` is a design in any accepted surface: the ``.arch`` language,
    the canonical schema JSON, or Structurizr DSL. The format is detected.

    Returns a JSON object with ``may_merge`` (false when any ERROR is present),
    ``blocking_count`` and the full ``findings`` list. Only deterministic rules
    run here; nothing probabilistic can change the merge verdict.
    """
    try:
        report = validate_source(source, include_implied=include_implied)
    except ModelError as exc:
        return json.dumps(
            {"may_merge": False, "error": "invalid_model", "detail": str(exc)},
            ensure_ascii=False,
        )
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
