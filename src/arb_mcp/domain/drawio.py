"""Export a canonical model to drawio (mxGraph) XML as separate C4 views.

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

from .model import Model, Node, Relation

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
    "verticalAlign=bottom;dashPattern=8 4;metaEdit=1;perimeter=rectanglePerimeter;"
    "container=1;collapsible=0;"
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


# ─────────────────────────── the three levels ───────────────────────────
def _view_c1(model: Model) -> Diagram:
    tops = [n for n in model.nodes if n.type in ("person", "softwareSystem")]
    top_ids = {n.id for n in tops}
    cells: list[str] = []
    y = 40
    for n in tops:
        cells.append(_c4_vertex(n, _STYLE.get(n.type, _EXTERNAL), 40, y, 210, 110))
        y += 150

    def resolve(nid: str) -> str | None:
        t = model.top_of(nid)
        return t if t in top_ids else None

    cells += _edges(_resolved(model, resolve))
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


def _view_c2(model: Model, system: Node) -> Diagram:
    sid = system.id
    containers = system.children_of_type("container")
    container_ids = {c.id for c in containers}
    cells: list[str] = []
    # boundary of the in-focus system, containers nested inside it
    ch = 100
    cells.append(
        _vertex(sid, _label(system), _BOUNDARY, 200, 40, 320, 60 + len(containers) * (ch + 20))
    )
    for i, c in enumerate(containers):
        cells.append(
            _c4_vertex(c, _STYLE["container"], 40, 40 + i * (ch + 20), 240, ch, parent=sid)
        )

    def resolve(nid: str) -> str | None:
        if nid not in model:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = model.lift_to(nid, container_ids)
        if inside is not None:
            return inside
        # the focus system itself resolves to its boundary, drawn with id=sid;
        # anything else, to its top-level element (an external)
        return model.top_of(nid)

    pairs = _resolved(model, resolve)
    ey = 40
    for ext in _externals(model, pairs, sid, container_ids):
        style = _STYLE["person"] if ext.type == "person" else _EXTERNAL
        cells.append(_c4_vertex(ext, style, 600, ey, 210, 110))
        ey += 150
    cells += _edges(pairs)
    return Diagram(
        level="C2",
        scope=sid,
        name=f"{system.name} — C2 Containers",
        xml=_mxfile(f"C2 {system.name}", cells),
    )


def _view_c3(model: Model, container: Node) -> Diagram:
    cid = container.id
    components = container.children_of_type("component")
    comp_ids = {c.id for c in components}
    cells: list[str] = []
    ch = 90
    cells.append(
        _vertex(cid, _label(container), _BOUNDARY, 200, 40, 320, 60 + len(components) * (ch + 20))
    )
    for i, c in enumerate(components):
        cells.append(
            _c4_vertex(c, _STYLE["component"], 40, 40 + i * (ch + 20), 240, ch, parent=cid)
        )

    def resolve(nid: str) -> str | None:
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

    pairs = _resolved(model, resolve)
    ey = 40
    for ext in _externals(model, pairs, cid, comp_ids):
        style = (
            _STYLE["person"]
            if ext.type == "person"
            else (_STYLE["container"] if ext.type == "container" else _EXTERNAL)
        )
        cells.append(_c4_vertex(ext, style, 600, ey, 210, 110))
        ey += 150
    cells += _edges(pairs)
    return Diagram(
        level="C3",
        scope=cid,
        name=f"{container.name} — C3 Components",
        xml=_mxfile(f"C3 {container.name}", cells),
    )


def to_c4_views(model: Model) -> list[Diagram]:
    """Return the C4 views as independent diagrams: one C1, one C2 per system
    with containers, one C3 per container with components. Each carries its own
    standalone ``.drawio`` XML — never tabs in one file."""
    views: list[Diagram] = [_view_c1(model)]
    views.extend(
        _view_c2(model, n)
        for n in model.nodes
        if n.type == "softwareSystem" and n.children_of_type("container")
    )
    views.extend(
        _view_c3(model, n)
        for n in model.walk()
        if n.type == "container" and n.children_of_type("component")
    )
    return views


def _flat_level(model: Model) -> str:
    t = model.spec.node_types
    if "actor" in t or "useCase" in t:
        return "UML"
    if "deploymentNode" in t:
        return "Deployment"
    return "Diagram"


_FLAT_PAD, _FLAT_HDR, _FLAT_GAP = 24, 36, 20


def _flat_measure(node: Node) -> tuple[int, int]:
    """Bottom-up size of a node: a leaf is a fixed box; a container grows to fit
    its stacked children at any depth."""
    if not node.nodes:
        return (70, 90) if node.type == "actor" else (200, 80)
    sizes = [_flat_measure(k) for k in node.nodes]
    w = max(s[0] for s in sizes) + 2 * _FLAT_PAD
    h = _FLAT_HDR + sum(s[1] for s in sizes) + _FLAT_GAP * (len(node.nodes) - 1) + _FLAT_PAD
    return w, h


def _view_flat(model: Model) -> Diagram:
    """A single diagram for any non-C4 notation (UML, deployment, …): every
    element drawn as itself, containers nesting their children to ARBITRARY
    depth, relations as edges. No lifting is lost — every node is emitted."""
    cells: list[str] = []
    emitted: set[str] = set()

    def place(node: Node, x: int, y: int, container: str) -> None:
        emitted.add(node.id)
        w, h = _flat_measure(node)
        if not node.nodes:
            style = _UML_STYLE.get(node.type, _UML_FALLBACK)
            cells.append(_vertex(node.id, _label(node), style, x, y, w, h, container))
            return
        cells.append(_vertex(node.id, _label(node), _UML_BOUNDARY, x, y, w, h, container))
        cy = _FLAT_HDR
        for k in node.nodes:  # children are placed in the container's own coordinates
            _kw, kh = _flat_measure(k)
            place(k, _FLAT_PAD, cy, node.id)
            cy += kh + _FLAT_GAP

    ty = 40
    for n in model.nodes:
        _w, h = _flat_measure(n)
        place(n, 40, ty, "1")
        ty += h + 50

    # every node is emitted, so an endpoint resolves to itself; a stray deeper id
    # (none here) would lift to the nearest drawn ancestor
    def resolve(nid: str) -> str | None:
        return model.lift_to(nid, emitted)

    cells += _edges(_resolved(model, resolve))
    level = _flat_level(model)
    return Diagram(
        level=level,
        scope=model.scope or "diagram",
        name=f"{model.name or 'Model'} — {level}",
        xml=_mxfile(level, cells),
    )


def to_views(model: Model) -> list[Diagram]:
    """Dispatch by notation: C4 models get the separate C1/C2/C3 views; any other
    spec (UML use cases, etc.) gets a single flat diagram. Same canonical model,
    the exporter reads its ``spec`` to decide."""
    return to_c4_views(model) if model.is_c4 else [_view_flat(model)]
