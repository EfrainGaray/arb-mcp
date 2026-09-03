"""stdio MCP adapter: the tools a host (Kiro) drives.

The server has NO LLM and calls none. It is a box of deterministic tools:
describe the contract, assemble a drafted model, validate it, convert it. The
agent supplies the thinking; these tools supply the ground truth.

The HTTP/SSE adapter (auth + audit, for CI) will share the exact same use cases.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from ...application.build_model import C4_SPEC, build_model
from ...application.check_catalog import check_catalog as _check_catalog
from ...application.convert_model import FORMATS, convert_source
from ...application.validate_model import validate_source
from ...domain.loading import SCHEMA, ModelError

mcp = MCPServer("arb-mcp")


@mcp.tool()
def describe_contract() -> str:
    """The contract to build a design against: the C4 spec (allowed node and
    relation types, and what each requires) and the normative JSON schema.

    An agent calls this first so it drafts elements of the right shape, instead
    of guessing. This is the deterministic replacement for a generation prompt.
    """
    return json.dumps({"spec": C4_SPEC, "schema": SCHEMA}, ensure_ascii=False, indent=2)


@mcp.tool()
def build_model_tool(
    nodes: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None = None,
    name: str = "",
) -> str:
    """Assemble a canonical model from drafted C4 elements and validate it.

    ``nodes``/``relations`` are what the agent drafted from the epic. The fixed
    C4 spec is injected here (the agent cannot invent types) and the result is
    held to the schema. Returns ``{ok, model, validation}``; on a malformed
    draft, ``{ok:false, error, detail}`` with the exact schema failure to fix.
    """
    try:
        built = build_model(nodes, relations or [], name=name)
    except ModelError as exc:
        return json.dumps({"ok": False, "error": "invalid_model", "detail": str(exc)},
                          ensure_ascii=False)
    return json.dumps(
        {"ok": True, "model": built.model, "validation": built.report.to_dict()},
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
def validate_model(source: str, include_implied: bool = False) -> str:
    """Validate a design and report whether it may merge.

    ``source`` is a design in any accepted surface — ``.arch``, canonical schema
    JSON, or Structurizr DSL; the format is detected. Returns ``may_merge``
    (false when any ERROR is present), ``blocking_count`` and all ``findings``.
    Only deterministic rules run here; nothing probabilistic changes the verdict.
    """
    try:
        report = validate_source(source, include_implied=include_implied)
    except ModelError as exc:
        return json.dumps({"may_merge": False, "error": "invalid_model", "detail": str(exc)},
                          ensure_ascii=False)
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool()
def convert_model(source: str, to: str = "drawio") -> str:
    """Export a design to another surface. ``to`` is one of: drawio, structurizr.

    ``source`` is a design in any accepted surface; the format is detected.
    drawio comes back as SEPARATE C4 views (one C1, one C2 per system, one C3
    per container), never tabbed. This is the Structurizr-DSL-to-drawio path.
    """
    try:
        return convert_source(source, to)
    except ModelError as exc:
        return json.dumps({"ok": False, "error": "invalid_model", "detail": str(exc)},
                          ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc), "formats": list(FORMATS)},
                          ensure_ascii=False)


@mcp.tool()
def check_catalog(source: str) -> str:
    """Reconcile a design against the architecture catalog (LeanIX, the source of
    truth): which components already exist there (with their catalog id) and
    which are new and must be registered to keep the catalog current.

    ``source`` is a design in any accepted surface; the format is detected.
    Informational only — it never blocks a merge. Needs LEANIX_BASE_URL and
    LEANIX_API_TOKEN in the environment.
    """
    from ...domain import loading
    from ...infra.leanix import from_env
    try:
        model = loading.load(source)
        report = _check_catalog(model, from_env())
    except (ModelError, RuntimeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps({"ok": True, **report.to_dict()}, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
