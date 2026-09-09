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

from .model import Model, Node

_C4_ELEMENT = {"person", "softwareSystem", "container", "component"}
_WITH_TECH = {"container", "component"}


def _q(text: str) -> str:
    # Structurizr DSL has no escape for a double quote inside a string, so a name
    # carrying one would silently corrupt on reload. Fold it to an apostrophe:
    # lossy but legible and guaranteed to round-trip.
    return '"' + str(text).replace('"', "'").replace("\n", " ").replace("\r", " ") + '"'


def _element(node: Node, depth: int, lines: list[str]) -> None:
    if node.type not in _C4_ELEMENT:
        return
    pad = "    " * depth
    head = f"{pad}{node.id} = {node.type} {_q(node.name)}"
    if node.description:
        head += f" {_q(node.description)}"
    if node.type in _WITH_TECH and node.technology:
        # description slot must be present before technology
        if not node.description:
            head += ' ""'
        head += f" {_q(node.technology)}"
    children = [c for c in node.nodes if c.type in _C4_ELEMENT]
    if children:
        lines.append(head + " {")
        for c in children:
            _element(c, depth + 1, lines)
        lines.append(pad + "}")
    else:
        lines.append(head)


def _is_c4_element(model: Model, node_id: str) -> bool:
    node = model.get(node_id)
    return node is not None and node.type in _C4_ELEMENT


def to_structurizr(model: Model) -> str:
    lines: list[str] = []
    header = f"workspace {_q(model.name or 'Workspace')}"
    if model.description:
        header += f" {_q(model.description)}"
    lines.append(header + " {")
    lines.append("    model {")

    for n in model.nodes:
        _element(n, 2, lines)

    for rel in model.written_relations():
        # both endpoints must be C4 elements that were actually declared above;
        # a relation to a decision (an ADR, not an element) would emit an
        # undeclared identifier that reloads dangling with a mutated type
        if not (_is_c4_element(model, rel.source) and _is_c4_element(model, rel.target)):
            continue
        line = f"        {rel.source} -> {rel.target}"
        if rel.description:
            line += f" {_q(rel.description)}"
        if rel.technology:
            if not rel.description:
                line += ' ""'
            line += f" {_q(rel.technology)}"
        lines.append(line)
    lines.append("    }")

    # views: one C1 landscape/context, one C2 per system, one C3 per container
    lines.append("    views {")
    lines.append("        systemLandscape {")
    lines.append("            include *")
    lines.append("            autolayout lr")
    lines.append("        }")
    for n in model.walk():
        if n.type == "softwareSystem" and n.children_of_type("container"):
            lines.append(f"        container {n.id} {{")
            lines.append("            include *")
            lines.append("            autolayout lr")
            lines.append("        }")
        if n.type == "container" and n.children_of_type("component"):
            lines.append(f"        component {n.id} {{")
            lines.append("            include *")
            lines.append("            autolayout lr")
            lines.append("        }")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"
