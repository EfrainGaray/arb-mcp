"""Per-level C4 diagram assembly: places C4View elements with a RenderProfile
and emits mxGraph cells.

This module answers "how" — geometry, styles, XML cell types — given a
C4View that already answers "what" (scope, externals, edges).
"""

from __future__ import annotations

from ..c4_views import C4View
from ..c4_views import c4_views as scoped_views
from ..layout import Box, Resolved
from ..model import Model, Node
from ..render import RenderProfile
from .cells import Diagram, c4_vertex, edges, label, mxfile, vertex
from .placing import cell_of, layout_for, place
from .styles import BOUNDARY, EXTERNAL, STYLE


# ─── C4-only helpers (private: not used outside this module) ──────────────────
def _emit_c4(placed: Resolved, node: Node, style: str, cells: list[str]) -> None:
    x, y, w, h, parent = cell_of(placed, node.id)
    cells.append(c4_vertex(node, style, x, y, w, h, parent=parent))


def _emit_boundary(placed: Resolved, node: Node, cells: list[str]) -> None:
    x, y, w, h, parent = cell_of(placed, node.id)
    cells.append(vertex(node.id, label(node), BOUNDARY, x, y, w, h, parent))


def _external_style(node: Node) -> str:
    if node.type == "person":
        return STYLE["person"]
    if node.type == "container":
        return STYLE["container"]
    return EXTERNAL


# ─── per-level view builders ──────────────────────────────────────────────────
def _view_c1(model: Model, profile: RenderProfile, view: C4View) -> Diagram:
    placed = place(
        [Box(n.id, None, profile.size_of(n.type)) for n in view.inside],
        layout_for(model, None),
        profile,
    )
    cells: list[str] = []
    for n in view.inside:
        _emit_c4(placed, n, STYLE.get(n.type, EXTERNAL), cells)
    cells += edges([(e.source, e.target, e.relation) for e in view.edges])
    return Diagram(
        level=view.level,
        scope=view.scope,
        name=view.name,
        xml=mxfile("C1 System Context", cells),
    )


def _view_focused(model: Model, profile: RenderProfile, view: C4View) -> Diagram:
    """C2 or C3: focus wrapped in a boundary, inside elements + externals placed."""
    if view.focus is None:
        raise ValueError(f"{view.level} view requires a focus node")
    focus = view.focus
    lyt = layout_for(model, focus.id)
    boxes = [Box(focus.id, None, profile.boundary_size)]
    boxes += [Box(c.id, focus.id, profile.size_of(c.type)) for c in view.inside]
    boxes += [Box(e.id, None, profile.size_of(e.type)) for e in view.externals]
    placed = place(boxes, lyt, profile)
    cells: list[str] = []
    _emit_boundary(placed, focus, cells)
    for c in view.inside:
        _emit_c4(placed, c, STYLE[c.type], cells)
    for e in view.externals:
        _emit_c4(placed, e, _external_style(e), cells)
    cells += edges([(e.source, e.target, e.relation) for e in view.edges])
    return Diagram(
        level=view.level,
        scope=view.scope,
        name=view.name,
        xml=mxfile(f"{view.level} {focus.name}", cells),
    )


def to_c4_views(model: Model, profile: RenderProfile | None = None) -> list[Diagram]:
    """Return the C4 views as independent diagrams: one C1, one C2 per system
    with containers, one C3 per container with components.  Enumeration order
    comes from ``c4_views.c4_views()`` so the drawio and mermaid exporters
    cannot diverge."""
    prof = profile or RenderProfile.load("c4")
    result: list[Diagram] = []
    for view in scoped_views(model):
        if view.level == "C1":
            result.append(_view_c1(model, prof, view))
        else:
            result.append(_view_focused(model, prof, view))
    return result
