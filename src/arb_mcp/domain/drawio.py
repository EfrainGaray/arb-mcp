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
    while parent.get(cur) is not None:
        cur = parent[cur]  # type: ignore[assignment]
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


def _vertex(cid: str, label: str, style: str, x: int, y: int, w: int, h: int,
            parent: str = "1") -> str:
    return (
        f'<mxCell id={quoteattr(cid)} value={quoteattr(label)} style={quoteattr(style)} '
        f'vertex="1" parent={quoteattr(parent)}>'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def _edge_cell(eid: str, label: str, src: str, dst: str) -> str:
    return (
        f'<mxCell id={quoteattr(eid)} value={quoteattr(label)} style={quoteattr(_EDGE)} '
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
        f'</mxGraphModel></diagram></mxfile>'
    )


def _rel_label(rel: dict[str, Any]) -> str:
    label = escape(str(rel.get("description", "")))
    if rel.get("technology"):
        tech = f"[{escape(str(rel['technology']))}]"
        label = f"{label}<br>{tech}" if label else tech
    return label


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
        cells.append(_vertex(n["id"], _label(n), style, 40, y, 200, 100))
        y += 140

    def resolve(nid: str) -> str | None:
        t = _top(nid, parent)
        return t if t in top_ids else None

    cells += _edges_between(model, resolve)
    return {"level": "C1", "scope": "system-landscape",
            "name": f"{model.get('name', 'Architecture')} — C1 System Context",
            "xml": _mxfile("C1 System Context", cells)}


def _view_c2(model: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    by_id, parent = _index(model)
    sid = system["id"]
    containers = [c for c in system.get("nodes", []) if c.get("type") == "container"]
    container_ids = {c["id"] for c in containers}
    cells: list[str] = []
    # boundary of the in-focus system, containers nested inside it
    ch = 100
    cells.append(_vertex(sid, _label(system), _BOUNDARY, 200, 40, 320,
                         60 + len(containers) * (ch + 20)))
    for i, c in enumerate(containers):
        cells.append(_vertex(c["id"], _label(c), _STYLE["container"],
                             40, 40 + i * (ch + 20), 240, ch, parent=sid))

    externals: dict[str, dict[str, Any]] = {}

    def resolve(nid: str) -> str | None:
        if nid not in by_id:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = _lift_to(nid, container_ids, parent)
        if inside is not None:
            return inside
        t = _top(nid, parent)
        if t == sid:
            return None  # inside the system but not a container (e.g. a component)
        externals[t] = by_id[t]
        return t

    edges = _edges_between(model, resolve)
    ey = 40
    for ext in externals.values():
        style = _STYLE["person"] if ext["type"] == "person" else _EXTERNAL
        cells.append(_vertex(ext["id"], _label(ext), style, 600, ey, 200, 90))
        ey += 130
    cells += edges
    return {"level": "C2", "scope": sid,
            "name": f"{system.get('name', sid)} — C2 Containers",
            "xml": _mxfile(f"C2 {system.get('name', sid)}", cells)}


def _view_c3(model: dict[str, Any], container: dict[str, Any],
             by_id: dict[str, dict[str, Any]], parent: dict[str, str | None]) -> dict[str, Any]:
    cid = container["id"]
    components = [c for c in container.get("nodes", []) if c.get("type") == "component"]
    comp_ids = {c["id"] for c in components}
    cells: list[str] = []
    ch = 90
    cells.append(_vertex(cid, _label(container), _BOUNDARY, 200, 40, 320,
                         60 + len(components) * (ch + 20)))
    for i, c in enumerate(components):
        cells.append(_vertex(c["id"], _label(c), _STYLE["component"],
                             40, 40 + i * (ch + 20), 240, ch, parent=cid))

    externals: dict[str, dict[str, Any]] = {}

    def resolve(nid: str) -> str | None:
        if nid not in by_id:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = _lift_to(nid, comp_ids, parent)
        if inside is not None:
            return inside
        # a sibling container, or a top-level system/person, represents the outside
        cur: str | None = nid
        while cur is not None:
            p = parent.get(cur)
            if p is None or by_id[cur].get("type") in ("container", "softwareSystem", "person"):
                if cur != cid:
                    externals[cur] = by_id[cur]
                    return cur
                return None
            cur = p
        return None

    edges = _edges_between(model, resolve)
    ey = 40
    for ext in externals.values():
        style = _STYLE["person"] if ext["type"] == "person" else (
            _STYLE["container"] if ext["type"] == "container" else _EXTERNAL)
        cells.append(_vertex(ext["id"], _label(ext), style, 600, ey, 200, 90))
        ey += 130
    cells += edges
    return {"level": "C3", "scope": cid,
            "name": f"{container.get('name', cid)} — C3 Components",
            "xml": _mxfile(f"C3 {container.get('name', cid)}", cells)}


def to_c4_views(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the C4 views as independent diagrams: one C1, one C2 per system
    with containers, one C3 per container with components. Each carries its own
    standalone ``.drawio`` XML — never tabs in one file."""
    by_id, parent = _index(model)
    views: list[dict[str, Any]] = [_view_c1(model)]
    for n in model.get("nodes", []):
        if n.get("type") == "softwareSystem" and any(
            c.get("type") == "container" for c in n.get("nodes", [])
        ):
            views.append(_view_c2(model, n))
    for node in by_id.values():
        if node.get("type") == "container" and any(
            c.get("type") == "component" for c in node.get("nodes", [])
        ):
            views.append(_view_c3(model, node, by_id, parent))
    return views
