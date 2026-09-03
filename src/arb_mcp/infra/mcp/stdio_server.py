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

from ...application.convert_model import FORMATS, convert_source
from ...application.generate_model import generate_design
from ...application.validate_model import validate_source
from ...domain.loading import ModelError
from ...infra.llm import from_env

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


@mcp.tool()
def generate_model(description: str, stories: list[str] | None = None, name: str = "") -> str:
    """Draft a C4 design from natural language: a prompt, an epic, or the text
    of a file (Jira/Markdown content is passed in as ``description``).

    Returns JSON with the generated ``.arch`` source, the canonical ``model``,
    and a ``validation`` report of that draft. This is generation, not a gate:
    ``validation.may_merge`` reflects the deterministic rules the draft still
    breaks, but this tool never blocks anything. Needs ARB_LLM_BASE_URL and
    ARB_LLM_MODEL in the environment.
    """
    try:
        llm = from_env()
        design = generate_design(llm, description, stories=stories or [], name=name)
    except (ModelError, RuntimeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(
        {"ok": True, "model": design.model, "validation": design.report.to_dict()},
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
def convert_model(source: str, to: str = "drawio") -> str:
    """Export a design to another surface. ``to`` is one of: drawio, arch.

    ``source`` is a design in any accepted surface (.arch / schema JSON /
    Structurizr DSL); the format is detected. drawio output is native,
    editable C4 XML using the real mxgraph.c4 stencil styles. This is the
    Structurizr-DSL-to-drawio path: pass the DSL, get the diagram.
    """
    try:
        out = convert_source(source, to)
    except ModelError as exc:
        return json.dumps({"ok": False, "error": "invalid_model", "detail": str(exc)},
                          ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc), "formats": list(FORMATS)},
                          ensure_ascii=False)
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
