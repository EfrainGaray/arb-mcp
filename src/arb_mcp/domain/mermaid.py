"""Export a canonical model to Mermaid C4 diagram text.

Mermaid's C4 syntax (C4Context / C4Container / C4Component) is what GitHub
and GitLab render natively.  This exporter consumes the same ``C4View``
objects that the drawio package does, so the two exporters cannot silently
diverge on which elements appear in which view.

Non-C4 models raise ``ValueError`` — Mermaid flowchart for UML/deployment
is not requested in the current brief.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._text import fold_quotes
from .c4_views import C4View, Edge, c4_views
from .model import Model, Node

# ─────────────────────────── data classes ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class MermaidDiagram:
    """One Mermaid C4 diagram: a level, its canonical scope, a human-readable
    title, and the raw Mermaid text."""

    level: str
    scope: str
    name: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "scope": self.scope,
            "name": self.name,
            "mermaid": self.text,
        }


# ─────────────────────────── shape tables ──────────────────────────────────
#
# Each table maps a C4 node type to its Mermaid shape keyword.  Argument
# positions differ by shape (Container/Component take a "technology" argument
# that Person/System do not), so the arity is encoded here rather than scattered
# in f-strings.

_DIAGRAM_TYPE: dict[str, str] = {
    "C1": "C4Context",
    "C2": "C4Container",
    "C3": "C4Component",
}

# Shapes for elements drawn *inside* the focus boundary (or as top-level in C1).
_INSIDE_SHAPE: dict[str, str] = {
    "person": "Person",
    "softwareSystem": "System",
    "container": "Container",
    "component": "Component",
}

# Shapes for external elements (reached by an edge, outside the focus boundary).
# Mirrors drawio's _external_style: person → Person, container → Container_Ext,
# everything else (softwareSystem) → System_Ext.
_EXT_SHAPE: dict[str, str] = {
    "person": "Person",
    "softwareSystem": "System_Ext",
    "container": "Container_Ext",
    "component": "Container_Ext",  # component appearing as external is unusual; treat as container
}

# Shapes for the focus boundary wrapper itself.
_BOUNDARY_SHAPE: dict[str, str] = {
    "softwareSystem": "System_Boundary",
    "container": "Container_Boundary",
}

# Shapes that take a "technology" argument: Container(id,"name","tech","desc").
_HAS_TECH: frozenset[str] = frozenset({"Container", "Component", "Container_Ext"})


# ─────────────────────────── emission helpers ──────────────────────────────

_INDENT = "    "


def _node_stmt(node: Node, shape: str, indent: str = _INDENT) -> str:
    n = fold_quotes(node.name)
    d = fold_quotes(node.description)
    if shape in _HAS_TECH:
        t = fold_quotes(node.technology)
        return f'{indent}{shape}({node.id}, "{n}", "{t}", "{d}")'
    return f'{indent}{shape}({node.id}, "{n}", "{d}")'


def _boundary_stmts(focus: Node, inside: tuple[Node, ...], indent: str = _INDENT) -> list[str]:
    shape = _BOUNDARY_SHAPE.get(focus.type, "System_Boundary")
    n = fold_quotes(focus.name)
    inner = indent + _INDENT
    lines: list[str] = [f'{indent}{shape}({focus.id}, "{n}") {{']
    for node in inside:
        child_shape = _INSIDE_SHAPE.get(node.type, "Component")
        lines.append(_node_stmt(node, child_shape, inner))
    lines.append(f"{indent}}}")
    return lines


def _rel_stmt(edge: Edge, indent: str = _INDENT) -> str:
    d = fold_quotes(edge.relation.description)
    t = fold_quotes(edge.relation.technology)
    if t:
        return f'{indent}Rel({edge.source}, {edge.target}, "{d}", "{t}")'
    return f'{indent}Rel({edge.source}, {edge.target}, "{d}")'


# ─────────────────────────── view builder ──────────────────────────────────


def _to_diagram(view: C4View) -> MermaidDiagram:
    diag_type = _DIAGRAM_TYPE[view.level]
    lines: list[str] = [diag_type, f"{_INDENT}title {fold_quotes(view.name)}"]

    if view.focus is None:
        # C1: all tops drawn as themselves; no boundary wrapper
        for node in view.inside:
            shape = _INSIDE_SHAPE.get(node.type, "System")
            lines.append(_node_stmt(node, shape))
    else:
        # C2/C3: focus wrapped in a boundary, externals outside
        lines.extend(_boundary_stmts(view.focus, view.inside))
        for node in view.externals:
            shape = _EXT_SHAPE.get(node.type, "System_Ext")
            lines.append(_node_stmt(node, shape))

    lines.extend(_rel_stmt(edge) for edge in view.edges)

    return MermaidDiagram(
        level=view.level,
        scope=view.scope,
        name=view.name,
        text="\n".join(lines) + "\n",
    )


# ─────────────────────────── public API ────────────────────────────────────


def to_c4_views(model: Model) -> list[MermaidDiagram]:
    """Export every C4 view of ``model`` as Mermaid C4 text.

    Raises ``ValueError`` for non-C4 models (UML, deployment, …) — a
    ``flowchart`` fallback is not in scope.  Enumeration order and scoping come
    from ``c4_views.c4_views()``; the drawio and mermaid exporters share that
    function and cannot diverge.
    """
    if not model.is_c4:
        raise ValueError("mermaid supports C4 models only")
    return [_to_diagram(v) for v in c4_views(model)]
