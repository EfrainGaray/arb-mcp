"""Export a canonical model to drawio (mxGraph) XML as separate C4 views.

The ONE drawio exporter: geometry comes from the ordinal resolver (``layout``)
over the view's ``rank``/``order`` cells, sizes and gaps from a ``RenderProfile``
the caller chooses, styles verbatim from drawio's own C4 palette. Nothing in the
model is a pixel; two profiles over the same model validate identically and
draw differently.

C4 is a set of diagrams at rising zoom, not one canvas: a System Context (C1),
one Container diagram (C2) per software system, and one Component diagram (C3)
per container. Each is emitted as its OWN standalone ``<mxfile>`` — never tabs
inside a single file — so a bank stores, reviews and versions each level on its
own.

Every style string is lifted verbatim from drawio's ``mxgraph.c4`` stencil
(``Sidebar-C4.js``): the person shape, the per-level fills (system #1061B0,
container #23A2D9, component #63BEF2), the dashed boundary and the ``blockThin``
edge. Nothing is invented; the output opens as native, editable C4 shapes.

These are views over the same canonical model the linter validates, so a diagram
and its verdict cannot drift.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from .layout import Box, Resolved, resolve
from .model import All, Inside, Layout, Model, Node, Relation
from .render import RenderProfile

# Verbatim from drawio's mxgraph.c4 stencil (Sidebar-C4.js).
_STYLE: dict[str, str] = {
    "person": (
        "html=1;fontSize=11;dashed=0;whiteSpace=wrap;fillColor=#083F75;"
        "strokeColor=#06315C;fontColor=#ffffff;shape=mxgraph.c4.person2;"
        "align=center;metaEdit=1;resizable=0;"
    ),
    "softwareSystem": (
        "rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor=#1061B0;"
        "fontColor=#ffffff;align=center;arcSize=10;strokeColor=#0D5091;metaEdit=1;resizable=0;"
    ),
    "container": (
        "rounded=1;whiteSpace=wrap;html=1;fontSize=11;labelBackgroundColor=none;"
        "fillColor=#23A2D9;fontColor=#ffffff;align=center;arcSize=10;strokeColor=#0E7DAD;"
        "metaEdit=1;resizable=0;"
    ),
    "component": (
        "rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor=#63BEF2;"
        "fontColor=#ffffff;align=center;arcSize=6;strokeColor=#2086C9;metaEdit=1;resizable=0;"
    ),
}
# An external software system, drawn as a plain grey box (out of focus).
_EXTERNAL = (
    "rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor=#8C8496;"
    "fontColor=#ffffff;align=center;arcSize=10;strokeColor=#736782;metaEdit=1;resizable=0;"
)
# The in-focus element (system in C2, container in C3): a dashed boundary.
_BOUNDARY = (
    "rounded=1;fontSize=11;whiteSpace=wrap;html=1;dashed=1;arcSize=20;fillColor=none;"
    "strokeColor=#666666;fontColor=#333333;labelBackgroundColor=none;align=left;"
    "verticalAlign=bottom;labelBorderColor=none;spacingTop=0;spacing=10;dashPattern=8 4;"
    "metaEdit=1;rotatable=0;perimeter=rectanglePerimeter;allowArrows=0;connectable=0;"
    "expand=0;recursiveResize=0;absoluteArcSize=1;container=1;collapsible=0;"
)
_EDGE = (
    "endArrow=blockThin;html=1;fontSize=10;fontColor=#404040;strokeWidth=1;endFill=1;"
    "strokeColor=#828282;elbow=vertical;metaEdit=1;endSize=14;startSize=14;jumpStyle=arc;"
    "jumpSize=16;rounded=0;edgeStyle=orthogonalEdgeStyle;"
)


# UML and generic shapes, standard drawio primitives. Used for any notation whose
# spec is not C4 — the same canonical model, a different stencil.
_UML_STYLE: dict[str, str] = {
    "actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
    "outlineConnect=0;",
    "useCase": "ellipse;whiteSpace=wrap;html=1;",
}
_UML_FALLBACK = "rounded=0;whiteSpace=wrap;html=1;"
_UML_BOUNDARY = (
    "rounded=0;whiteSpace=wrap;html=1;dashed=1;verticalAlign=top;"
    "align=center;fillColor=none;strokeColor=#666666;container=1;collapsible=0;"
)


@dataclass(frozen=True, slots=True)
class Diagram:
    """One standalone drawio file: a C4 level (or a flat notation) over a scope."""

    level: str
    scope: str
    name: str
    xml: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "scope": self.scope, "name": self.name, "xml": self.xml}


# ─────────────────────────── xml emit ───────────────────────────
def _label(node: Node) -> str:
    parts = [f"<b>{escape(node.name)}</b>"]
    if node.technology:
        parts.append(f"[{escape(node.technology)}]")
    if node.description:
        parts.append(escape(node.description))
    return "<br>".join(parts)


_C4_TYPE_LABEL = {
    "person": "Person",
    "softwareSystem": "Software System",
    "container": "Container",
    "component": "Component",
}
_C4_LABEL_PLAIN = (
    '<font style="font-size: 16px"><b>%c4Name%</b></font>'
    '<div>[%c4Type%]</div><br><div><font style="font-size: 11px">'
    '<font color="#cccccc">%c4Description%</font></div>'
)
_C4_LABEL_TECH = (
    '<font style="font-size: 16px"><b>%c4Name%</b></font>'
    '<div>[%c4Type%: %c4Technology%]</div><br><div><font style="font-size: 11px">'
    '<font color="#E6E6E6">%c4Description%</font></div>'
)


def _c4_vertex(node: Node, style: str, x: int, y: int, w: int, h: int, parent: str = "1") -> str:
    """A native drawio C4 element: an <object> with c4* attributes and a
    placeholder label, exactly as drawio's own C4 shape library builds it — so
    it opens as a real C4 card (name, [Type: Technology], description), not a
    plain coloured box."""
    label = _C4_LABEL_TECH if node.type in ("container", "component") else _C4_LABEL_PLAIN
    attrs = [
        f"label={quoteattr(label)}",
        'placeholders="1"',
        f"c4Name={quoteattr(node.name)}",
        f"c4Type={quoteattr(_C4_TYPE_LABEL.get(node.type, node.type))}",
    ]
    if node.technology:
        attrs.append(f"c4Technology={quoteattr(node.technology)}")
    attrs.append(f"c4Description={quoteattr(node.description)}")
    attrs.append(f"id={quoteattr(node.id)}")
    return (
        f"<object {' '.join(attrs)}>"
        f'<mxCell style={quoteattr(style)} vertex="1" parent={quoteattr(parent)}>'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell></object>'
    )


def _vertex(
    cid: str, label: str, style: str, x: int, y: int, w: int, h: int, parent: str = "1"
) -> str:
    return (
        f"<mxCell id={quoteattr(cid)} value={quoteattr(label)} style={quoteattr(style)} "
        f'vertex="1" parent={quoteattr(parent)}>'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def _edge_cell(eid: str, label: str, src: str, dst: str) -> str:
    return (
        f"<mxCell id={quoteattr(eid)} value={quoteattr(label)} style={quoteattr(_EDGE)} "
        f'edge="1" parent="1" source={quoteattr(src)} target={quoteattr(dst)}>'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def _mxfile(name: str, cells: list[str]) -> str:
    body = "".join(cells)
    return (
        f'<mxfile host="arb-mcp"><diagram name={quoteattr(name)}>'
        f'<mxGraphModel dx="800" dy="600" grid="1" gridSize="10" guides="1" tooltips="1" '
        f'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" '
        f'pageHeight="1100" math="0" shadow="0">'
        f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root>'
        f"</mxGraphModel></diagram></mxfile>"
    )


def _rel_label(rel: Relation) -> str:
    label = escape(rel.description)
    if rel.technology:
        tech = f"[{escape(rel.technology)}]"
        label = f"{label}<br>{tech}" if label else tech
    return label


Resolver = Callable[[str], str | None]


def _resolved(model: Model, resolve: Resolver) -> list[tuple[str, str, Relation]]:
    """Every written relation collapsed to its visible endpoints, deduped by
    pair. ``resolve(id)`` returns the visible cell id for an endpoint, or None if
    the endpoint has no representative in this view. Both the edges and the
    externals a view draws come from this one list, so a box only appears when
    an edge to it actually survives."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, Relation]] = []
    for rel in model.written_relations():
        a, b = resolve(rel.source), resolve(rel.target)
        if a is None or b is None or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append((a, b, rel))
    return out


def _edges(pairs: list[tuple[str, str, Relation]]) -> list[str]:
    return [_edge_cell(f":e{i}", _rel_label(rel), a, b) for i, (a, b, rel) in enumerate(pairs)]


# ─────────────────────────── placing a view ───────────────────────────
_VIRTUAL = "_outside"  # an undrawn group: the externals of a C2/C3, stacked beside the focus


def _layout_for(model: Model, focus: str | None) -> Layout | None:
    """The authored layout of the view over ``focus`` (``None`` = the landscape)."""
    for v in model.views:
        if v.layout is None:
            continue
        for q in v.include:
            if focus is None and isinstance(q, All):
                return v.layout
            if isinstance(q, Inside) and q.node == focus:
                return v.layout
    return None


def _place(boxes: list[Box], layout: Layout | None, profile: RenderProfile) -> Resolved:
    return resolve(tuple(boxes), layout, profile.grid)


def _cell_of(placed: Resolved, node_id: str) -> tuple[int, int, int, int, str]:
    """x, y, w, h and the drawio parent id of a placed node. A child of the
    virtual group is lifted onto the canvas by the group's own offset."""
    p = placed.get(node_id)
    if p is None:
        return 0, 0, 0, 0, "1"
    if p.parent == _VIRTUAL:
        g = placed.get(_VIRTUAL)
        gx, gy = (g.x, g.y) if g else (0, 0)
        return gx + p.x, gy + p.y, p.w, p.h, "1"
    return p.x, p.y, p.w, p.h, p.parent or "1"


def _emit_c4(placed: Resolved, node: Node, style: str, cells: list[str]) -> None:
    x, y, w, h, parent = _cell_of(placed, node.id)
    cells.append(_c4_vertex(node, style, x, y, w, h, parent=parent))


def _emit_boundary(placed: Resolved, node: Node, cells: list[str]) -> None:
    x, y, w, h, parent = _cell_of(placed, node.id)
    cells.append(_vertex(node.id, _label(node), _BOUNDARY, x, y, w, h, parent))


def _external_style(node: Node) -> str:
    if node.type == "person":
        return _STYLE["person"]
    if node.type == "container":
        return _STYLE["container"]
    return _EXTERNAL


# ─────────────────────────── the three levels ───────────────────────────
def _view_c1(model: Model, profile: RenderProfile) -> Diagram:
    tops = [n for n in model.nodes if n.type in ("person", "softwareSystem")]
    top_ids = {n.id for n in tops}
    placed = _place(
        [Box(n.id, None, profile.size_of(n.type)) for n in tops], _layout_for(model, None), profile
    )
    cells: list[str] = []
    for n in tops:
        _emit_c4(placed, n, _STYLE.get(n.type, _EXTERNAL), cells)

    def resolve_end(nid: str) -> str | None:
        t = model.top_of(nid)
        return t if t in top_ids else None

    cells += _edges(_resolved(model, resolve_end))
    return Diagram(
        level="C1",
        scope="system-landscape",
        name=f"{model.name or 'Architecture'} — C1 System Context",
        xml=_mxfile("C1 System Context", cells),
    )


def _externals(
    model: Model, pairs: list[tuple[str, str, Relation]], focus: str, inside: set[str]
) -> list[Node]:
    """The elements outside the focus that an edge actually reaches, in first-seen order."""
    seen: dict[str, Node] = {}
    for a, b, _ in pairs:
        for end in (a, b):
            if end != focus and end not in inside and end not in seen:
                node = model.get(end)
                if node is not None:
                    seen[end] = node
    return list(seen.values())


def _focused(
    model: Model,
    profile: RenderProfile,
    focus: Node,
    inside: tuple[Node, ...],
    resolve_end: Callable[[str], str | None],
) -> tuple[list[str], list[tuple[str, str, Relation]]]:
    """The shared shape of C2 and C3: a boundary around the focus with its
    children nested, the externals an edge reaches beside it, the edges."""
    inside_ids = {c.id for c in inside}
    pairs = _resolved(model, resolve_end)
    externals = _externals(model, pairs, focus.id, inside_ids)
    layout = _layout_for(model, focus.id)
    boxes = [Box(focus.id, None, profile.boundary_size)]
    boxes += [Box(c.id, focus.id, profile.size_of(c.type)) for c in inside]
    if layout is None and externals:
        # No authored cells: stack the externals in a column beside the boundary,
        # inside an undrawn group so the resolver keeps them off the boundary's row.
        boxes.append(Box(_VIRTUAL, None, (0, 0)))
        boxes += [Box(e.id, _VIRTUAL, profile.size_of(e.type)) for e in externals]
    else:
        boxes += [Box(e.id, None, profile.size_of(e.type)) for e in externals]
    placed = _place(boxes, layout, profile)
    cells: list[str] = []
    _emit_boundary(placed, focus, cells)
    for c in inside:
        _emit_c4(placed, c, _STYLE[c.type], cells)
    for e in externals:
        _emit_c4(placed, e, _external_style(e), cells)
    cells += _edges(pairs)
    return cells, pairs


def _view_c2(model: Model, system: Node, profile: RenderProfile) -> Diagram:
    sid = system.id
    containers = system.children_of_type("container")
    container_ids = {c.id for c in containers}

    def resolve_end(nid: str) -> str | None:
        if nid not in model:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = model.lift_to(nid, container_ids)
        # the focus system itself resolves to its boundary, drawn with id=sid;
        # anything else, to its top-level element (an external)
        return inside if inside is not None else model.top_of(nid)

    cells, _ = _focused(model, profile, system, containers, resolve_end)
    return Diagram(
        level="C2",
        scope=sid,
        name=f"{system.name} — C2 Containers",
        xml=_mxfile(f"C2 {system.name}", cells),
    )


def _view_c3(model: Model, container: Node, profile: RenderProfile) -> Diagram:
    cid = container.id
    components = container.children_of_type("component")
    comp_ids = {c.id for c in components}

    def resolve_end(nid: str) -> str | None:
        if nid not in model:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = model.lift_to(nid, comp_ids)
        if inside is not None:
            return inside
        # a sibling container, a top-level system/person, or the focus container
        # itself (its boundary, drawn with id=cid) represents the endpoint
        cur: str | None = nid
        while cur is not None:
            node = model.get(cur)
            if node is None:
                return None
            p = model.parent_of(cur)
            if p is None or node.type in ("container", "softwareSystem", "person"):
                return cur
            cur = p
        return None

    cells, _ = _focused(model, profile, container, components, resolve_end)
    return Diagram(
        level="C3",
        scope=cid,
        name=f"{container.name} — C3 Components",
        xml=_mxfile(f"C3 {container.name}", cells),
    )


def to_c4_views(model: Model, profile: RenderProfile | None = None) -> list[Diagram]:
    """Return the C4 views as independent diagrams: one C1, one C2 per system
    with containers, one C3 per container with components. Each carries its own
    standalone ``.drawio`` XML — never tabs in one file."""
    prof = profile or RenderProfile.load("c4")
    views: list[Diagram] = [_view_c1(model, prof)]
    views.extend(
        _view_c2(model, n, prof)
        for n in model.nodes
        if n.type == "softwareSystem" and n.children_of_type("container")
    )
    views.extend(
        _view_c3(model, n, prof)
        for n in model.walk()
        if n.type == "container" and n.children_of_type("component")
    )
    return views


# ─────────────────────────── any other notation ───────────────────────────
def _flat_level(model: Model) -> str:
    t = model.spec.node_types
    if "actor" in t or "useCase" in t:
        return "UML"
    if "deploymentNode" in t:
        return "Deployment"
    return "Diagram"


def _view_flat(model: Model, profile: RenderProfile) -> Diagram:
    """A single diagram for any non-C4 notation (UML, deployment, …): every
    element drawn as itself, containers nesting their children to ARBITRARY
    depth, relations as edges. No lifting is lost — every node is emitted."""
    boxes = [Box(n.id, model.parent_of(n.id), profile.size_of(n.type)) for n in model.walk()]
    placed = _place(boxes, _layout_for(model, None), profile)
    cells: list[str] = []
    for n in model.walk():
        x, y, w, h, parent = _cell_of(placed, n.id)
        style = _UML_BOUNDARY if n.nodes else _UML_STYLE.get(n.type, _UML_FALLBACK)
        cells.append(_vertex(n.id, _label(n), style, x, y, w, h, parent))
    emitted = {n.id for n in model.walk()}

    def resolve_end(nid: str) -> str | None:
        return model.lift_to(nid, emitted)

    cells += _edges(_resolved(model, resolve_end))
    level = _flat_level(model)
    return Diagram(
        level=level,
        scope=model.scope or "diagram",
        name=f"{model.name or 'Model'} — {level}",
        xml=_mxfile(level, cells),
    )


def to_views(model: Model, profile: RenderProfile | None = None) -> list[Diagram]:
    """Dispatch by notation: C4 models get the separate C1/C2/C3 views; any other
    spec (UML use cases, etc.) gets a single flat diagram. Same canonical model,
    the exporter reads its ``spec`` to decide which shipped profile applies when
    the caller names none."""
    if model.is_c4:
        return to_c4_views(model, profile)
    return [_view_flat(model, profile or RenderProfile.load("generic"))]
