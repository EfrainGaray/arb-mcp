"""Export a canonical model to Structurizr DSL.

The inverse of ``_engine/from_structurizr``: canonical model out to the text
surface the bank already writes today. One exporter among several — same model
the linter validated, so the DSL and its verdict cannot drift.

Covers the C4 model surface (person, softwareSystem, container, component),
relations, and the C1/C2/C3 views. Types with no inline element syntax in
Structurizr (a ``decision`` is an ADR, not a model element) are skipped; the
caller keeps them in the canonical model regardless.
"""

from __future__ import annotations

from typing import Any

_C4_ELEMENT = {"person", "softwareSystem", "container", "component"}
_WITH_TECH = {"container", "component"}


def _q(text: Any) -> str:
    # Structurizr DSL has no escape for a double quote inside a string, so a name
    # carrying one would silently corrupt on reload. Fold it to an apostrophe:
    # lossy but legible and guaranteed to round-trip.
    return '"' + str(text).replace('"', "'").replace("\n", " ").replace("\r", " ") + '"'


def _element(node: dict[str, Any], depth: int, lines: list[str]) -> None:
    ntype = node.get("type", "")
    if ntype not in _C4_ELEMENT:
        return
    pad = "    " * depth
    head = f"{pad}{node['id']} = {ntype} {_q(node.get('name', node['id']))}"
    if node.get("description"):
        head += f" {_q(node['description'])}"
    if ntype in _WITH_TECH and node.get("technology"):
        # description slot must be present before technology
        if not node.get("description"):
            head += ' ""'
        head += f" {_q(node['technology'])}"
    children = [c for c in node.get("nodes", []) if c.get("type") in _C4_ELEMENT]
    if children:
        lines.append(head + " {")
        for c in children:
            _element(c, depth + 1, lines)
        lines.append(pad + "}")
    else:
        lines.append(head)


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.get("nodes", [])))
    return out


def to_structurizr(model: dict[str, Any]) -> str:
    lines: list[str] = []
    name = model.get("name", "Workspace")
    desc = model.get("description", "")
    header = f"workspace {_q(name)}"
    if desc:
        header += f" {_q(desc)}"
    lines.append(header + " {")
    lines.append("    model {")

    tops = [n for n in model.get("nodes", []) if n.get("type") in _C4_ELEMENT]
    for n in tops:
        _element(n, 2, lines)

    by_id = {n["id"]: n for n in _walk(model.get("nodes", []))}
    for rel in model.get("relations", []):
        if "implied" in (rel.get("tags") or []):
            continue
        # both endpoints must be C4 elements that were actually declared above;
        # a relation to a decision (an ADR, not an element) would emit an
        # undeclared identifier that reloads dangling with a mutated type
        if by_id.get(rel["from"], {}).get("type") not in _C4_ELEMENT:
            continue
        if by_id.get(rel["to"], {}).get("type") not in _C4_ELEMENT:
            continue
        line = f"        {rel['from']} -> {rel['to']}"
        if rel.get("description"):
            line += f" {_q(rel['description'])}"
        if rel.get("technology"):
            if not rel.get("description"):
                line += ' ""'
            line += f" {_q(rel['technology'])}"
        lines.append(line)
    lines.append("    }")

    # views: one C1 landscape/context, one C2 per system, one C3 per container
    lines.append("    views {")
    lines.append("        systemLandscape {")
    lines.append("            include *")
    lines.append("            autolayout lr")
    lines.append("        }")
    for n in _walk(model.get("nodes", [])):
        if n.get("type") == "softwareSystem" and any(
            c.get("type") == "container" for c in n.get("nodes", [])
        ):
            lines.append(f"        container {n['id']} {{")
            lines.append("            include *")
            lines.append("            autolayout lr")
            lines.append("        }")
        if n.get("type") == "container" and any(
            c.get("type") == "component" for c in n.get("nodes", [])
        ):
            lines.append(f"        component {n['id']} {{")
            lines.append("            include *")
            lines.append("            autolayout lr")
            lines.append("        }")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"
