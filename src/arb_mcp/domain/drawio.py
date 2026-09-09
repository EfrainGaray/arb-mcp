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

from typing import Any
from xml.sax.saxutils import escape, quoteattr

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


def _is_c4(model: dict[str, Any]) -> bool:
    types = (model.get("spec") or {}).get("nodeTypes") or {}
    return "softwareSystem" in types and "container" in types


# ─────────────────────────── model indexing ───────────────────────────
def _index(model: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str | None]]:
    by_id: dict[str, dict[str, Any]] = {}
    parent: dict[str, str | None] = {}

    def walk(nodes: list[dict[str, Any]], up: str | None) -> None:
        for n in nodes:
            by_id[n["id"]] = n
            parent[n["id"]] = up
            walk(n.get("nodes", []), n["id"])

    walk(model.get("nodes", []), None)
    return by_id, parent


def _top(nid: str, parent: dict[str, str | None]) -> str:
    cur = nid
    while (up := parent.get(cur)) is not None:
        cur = up
    return cur


def _lift_to(nid: str, wanted: set[str], parent: dict[str, str | None]) -> str | None:
    """The ancestor of ``nid`` (including itself) that is in ``wanted``, else None."""
    cur: str | None = nid
    while cur is not None:
        if cur in wanted:
            return cur
        cur = parent.get(cur)
    return None


# ─────────────────────────── xml emit ───────────────────────────
def _label(node: dict[str, Any]) -> str:
    name = escape(str(node.get("name", node["id"])))
    parts = [f"<b>{name}</b>"]
    if node.get("technology"):
        parts.append(f"[{escape(str(node['technology']))}]")
    if node.get("description"):
        parts.append(escape(str(node["description"])))
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


def _c4_vertex(
    node: dict[str, Any], style: str, x: int, y: int, w: int, h: int, parent: str = "1"
) -> str:
    """A native drawio C4 element: an <object> with c4* attributes and a
    placeholder label, exactly as drawio's own C4 shape library builds it — so
    it opens as a real C4 card (name, [Type: Technology], description), not a
    plain coloured box."""
    ntype = node.get("type", "")
    tech = node.get("technology")
    label = _C4_LABEL_TECH if ntype in ("container", "component") else _C4_LABEL_PLAIN
    attrs = [
        f"label={quoteattr(label)}",
        'placeholders="1"',
        f"c4Name={quoteattr(str(node.get('name', node['id'])))}",
        f"c4Type={quoteattr(_C4_TYPE_LABEL.get(ntype, ntype))}",
    ]
    if tech:
        attrs.append(f"c4Technology={quoteattr(str(tech))}")
    attrs.append(f"c4Description={quoteattr(str(node.get('description', '')))}")
    attrs.append(f"id={quoteattr(node['id'])}")
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


def _rel_label(rel: dict[str, Any]) -> str:
    label = escape(str(rel.get("description", "")))
    if rel.get("technology"):
        tech = f"[{escape(str(rel['technology']))}]"
        label = f"{label}<br>{tech}" if label else tech
    return label


def _resolved_pairs(model: dict[str, Any], resolve: Any) -> list[tuple[str, str]]:
    """Every declared relation collapsed to its visible endpoints, deduped —
    the same set ``_edges_between`` draws. Used to decide which externals to draw
    so a box only appears when an edge to it actually survives."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for rel in model.get("relations", []):
        if "implied" in (rel.get("tags") or []):
            continue
        a, b = resolve(rel["from"]), resolve(rel["to"])
        if a is None or b is None or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append((a, b))
    return out


def _edges_between(model: dict[str, Any], resolve: Any) -> list[str]:
    """Collapse every declared relation to its visible endpoints and dedupe.

    ``resolve(id)`` returns the visible cell id for an endpoint, or None if the
    endpoint has no representative in this view. Derived (``implied``) relations
    are skipped: they are not the author's diagram.
    """
    seen: set[tuple[str, str]] = set()
    out: list[str] = []
    for rel in model.get("relations", []):
        if "implied" in (rel.get("tags") or []):
            continue
        a, b = resolve(rel["from"]), resolve(rel["to"])
        if a is None or b is None or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append(_edge_cell(f":e{len(out)}", _rel_label(rel), a, b))
    return out


# ─────────────────────────── the three levels ───────────────────────────
def _view_c1(model: dict[str, Any]) -> dict[str, Any]:
    _, parent = _index(model)
    tops = [n for n in model.get("nodes", []) if n.get("type") in ("person", "softwareSystem")]
    top_ids = {n["id"] for n in tops}
    cells: list[str] = []
    y = 40
    for n in tops:
        style = _STYLE.get(n["type"], _EXTERNAL)
        cells.append(_c4_vertex(n, style, 40, y, 210, 110))
        y += 150

    def resolve(nid: str) -> str | None:
        t = _top(nid, parent)
        return t if t in top_ids else None

    cells += _edges_between(model, resolve)
    return {
        "level": "C1",
        "scope": "system-landscape",
        "name": f"{model.get('name', 'Architecture')} — C1 System Context",
        "xml": _mxfile("C1 System Context", cells),
    }


def _view_c2(model: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    by_id, parent = _index(model)
    sid = system["id"]
    containers = [c for c in system.get("nodes", []) if c.get("type") == "container"]
    container_ids = {c["id"] for c in containers}
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
        if nid not in by_id:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = _lift_to(nid, container_ids, parent)
        if inside is not None:
            return inside
        # the focus system itself resolves to its boundary, drawn with id=sid;
        # anything else, to its top-level element (an external)
        return sid if _top(nid, parent) == sid else _top(nid, parent)

    # externals are collected only from relations that actually survive, so a
    # dropped edge never leaves an orphan box floating in the diagram
    externals: dict[str, dict[str, Any]] = {}
    for a, b in _resolved_pairs(model, resolve):
        for end in (a, b):
            if end != sid and end not in container_ids:
                externals[end] = by_id[end]

    ey = 40
    for ext in externals.values():
        style = _STYLE["person"] if ext["type"] == "person" else _EXTERNAL
        cells.append(_c4_vertex(ext, style, 600, ey, 210, 110))
        ey += 150
    cells += _edges_between(model, resolve)
    return {
        "level": "C2",
        "scope": sid,
        "name": f"{system.get('name', sid)} — C2 Containers",
        "xml": _mxfile(f"C2 {system.get('name', sid)}", cells),
    }


def _view_c3(
    model: dict[str, Any],
    container: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    parent: dict[str, str | None],
) -> dict[str, Any]:
    cid = container["id"]
    components = [c for c in container.get("nodes", []) if c.get("type") == "component"]
    comp_ids = {c["id"] for c in components}
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
        if nid not in by_id:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = _lift_to(nid, comp_ids, parent)
        if inside is not None:
            return inside
        # a sibling container, a top-level system/person, or the focus container
        # itself (its boundary, drawn with id=cid) represents the endpoint
        cur: str | None = nid
        while cur is not None:
            p = parent.get(cur)
            if p is None or by_id[cur].get("type") in ("container", "softwareSystem", "person"):
                return cur
            cur = p
        return None

    externals: dict[str, dict[str, Any]] = {}
    for a, b in _resolved_pairs(model, resolve):
        for end in (a, b):
            if end != cid and end not in comp_ids:
                externals[end] = by_id[end]

    ey = 40
    for ext in externals.values():
        style = (
            _STYLE["person"]
            if ext["type"] == "person"
            else (_STYLE["container"] if ext["type"] == "container" else _EXTERNAL)
        )
        cells.append(_c4_vertex(ext, style, 600, ey, 210, 110))
        ey += 150
    cells += _edges_between(model, resolve)
    return {
        "level": "C3",
        "scope": cid,
        "name": f"{container.get('name', cid)} — C3 Components",
        "xml": _mxfile(f"C3 {container.get('name', cid)}", cells),
    }


def to_c4_views(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the C4 views as independent diagrams: one C1, one C2 per system
    with containers, one C3 per container with components. Each carries its own
    standalone ``.drawio`` XML — never tabs in one file."""
    by_id, parent = _index(model)
    views: list[dict[str, Any]] = [_view_c1(model)]
    views.extend(
        _view_c2(model, n)
        for n in model.get("nodes", [])
        if n.get("type") == "softwareSystem"
        and any(c.get("type") == "container" for c in n.get("nodes", []))
    )
    views.extend(
        _view_c3(model, node, by_id, parent)
        for node in by_id.values()
        if node.get("type") == "container"
        and any(c.get("type") == "component" for c in node.get("nodes", []))
    )
    return views


def _flat_level(model: dict[str, Any]) -> str:
    t = set((model.get("spec") or {}).get("nodeTypes") or {})
    if "actor" in t or "useCase" in t:
        return "UML"
    if "deploymentNode" in t:
        return "Deployment"
    return "Diagram"


_FLAT_PAD, _FLAT_HDR, _FLAT_GAP = 24, 36, 20


def _flat_measure(node: dict[str, Any]) -> tuple[int, int]:
    """Bottom-up size of a node: a leaf is a fixed box; a container grows to fit
    its stacked children at any depth."""
    kids = node.get("nodes", [])
    if not kids:
        return (70, 90) if node.get("type") == "actor" else (200, 80)
    sizes = [_flat_measure(k) for k in kids]
    w = max(s[0] for s in sizes) + 2 * _FLAT_PAD
    h = _FLAT_HDR + sum(s[1] for s in sizes) + _FLAT_GAP * (len(kids) - 1) + _FLAT_PAD
    return w, h


def _view_flat(model: dict[str, Any]) -> dict[str, Any]:
    """A single diagram for any non-C4 notation (UML, deployment, …): every
    element drawn as itself, containers nesting their children to ARBITRARY
    depth, relations as edges. No lifting is lost — every node is emitted."""
    _, parent = _index(model)
    cells: list[str] = []
    emitted: set[str] = set()

    def place(node: dict[str, Any], x: int, y: int, container: str) -> None:
        emitted.add(node["id"])
        w, h = _flat_measure(node)
        kids = node.get("nodes", [])
        if not kids:
            style = _UML_STYLE.get(node.get("type", ""), _UML_FALLBACK)
            cells.append(_vertex(node["id"], _label(node), style, x, y, w, h, container))
            return
        cells.append(_vertex(node["id"], _label(node), _UML_BOUNDARY, x, y, w, h, container))
        cy = _FLAT_HDR
        for k in kids:  # children are placed in the container's own coordinates
            _kw, kh = _flat_measure(k)
            place(k, _FLAT_PAD, cy, node["id"])
            cy += kh + _FLAT_GAP

    ty = 40
    for n in model.get("nodes", []):
        _w, h = _flat_measure(n)
        place(n, 40, ty, "1")
        ty += h + 50

    # every node is emitted, so an endpoint resolves to itself; a stray deeper id
    # (none here) would lift to the nearest drawn ancestor
    def resolve(nid: str) -> str | None:
        return _lift_to(nid, emitted, parent)

    cells += _edges_between(model, resolve)
    level = _flat_level(model)
    return {
        "level": level,
        "scope": model.get("scope", "diagram"),
        "name": f"{model.get('name', 'Model')} — {level}",
        "xml": _mxfile(level, cells),
    }


def to_views(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispatch by notation: C4 models get the separate C1/C2/C3 views; any other
    spec (UML use cases, etc.) gets a single flat diagram. Same canonical model,
    the exporter reads its ``spec`` to decide."""
    return to_c4_views(model) if _is_c4(model) else [_view_flat(model)]
