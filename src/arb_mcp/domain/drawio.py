"""Export a canonical model to drawio (mxGraph) XML using real C4 stencil styles.

The style strings are lifted verbatim from drawio's own C4 shape library
(``Sidebar-C4.js``, the ``mxgraph.c4`` stencil): the person shape, the per-level
fill colours (system #1061B0, container #23A2D9, component #63BEF2), the dashed
boundary and the ``blockThin`` relationship edge. Nothing here is invented — the
output opens in drawio as native, editable C4 shapes.

The model is the source of truth; this is one exporter among several (Structurizr,
Mermaid, ``.arch``). It walks the same canonical model the linter validates, so a
diagram and its verdict can never drift apart.
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
# A node with children that is not itself a C4 element box: draw it as a boundary.
_BOUNDARY = (
    "rounded=1;fontSize=11;whiteSpace=wrap;html=1;dashed=1;arcSize=20;fillColor=none;"
    "strokeColor=#666666;fontColor=#333333;labelBackgroundColor=none;align=left;"
    "verticalAlign=bottom;dashPattern=8 4;metaEdit=1;perimeter=rectanglePerimeter;"
    "container=1;collapsible=0;"
)
_FALLBACK = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#8C8496;fontColor=#ffffff;"
    "align=center;arcSize=10;strokeColor=#736782;metaEdit=1;resizable=0;"
)
_EDGE = (
    "endArrow=blockThin;html=1;fontSize=10;fontColor=#404040;strokeWidth=1;endFill=1;"
    "strokeColor=#828282;elbow=vertical;metaEdit=1;endSize=14;startSize=14;jumpStyle=arc;"
    "jumpSize=16;rounded=0;edgeStyle=orthogonalEdgeStyle;"
)


def _label(node: dict[str, Any]) -> str:
    name = escape(str(node.get("name", node["id"])))
    tech = node.get("technology")
    desc = node.get("description")
    parts = [f"<b>{name}</b>"]
    if tech:
        parts.append(f"[{escape(str(tech))}]")
    if desc:
        parts.append(escape(str(desc)))
    return "<br>".join(parts)


def _style_for(node: dict[str, Any]) -> str:
    ntype = node.get("type", "")
    if node.get("nodes") and ntype not in _STYLE:
        return _BOUNDARY
    return _STYLE.get(ntype, _FALLBACK)


def to_drawio(model: dict[str, Any]) -> str:
    """Return a self-contained drawio XML document for ``model``."""
    cells: list[str] = []
    x, y = 40, 40

    def emit(node: dict[str, Any], parent: str) -> None:
        nonlocal x, y
        cid = node["id"]
        style = _style_for(node)
        is_box = bool(node.get("nodes"))
        w, h = (240, 160) if is_box else (180, 90)
        cells.append(
            f'<mxCell id={quoteattr(cid)} value={quoteattr(_label(node))} '
            f'style={quoteattr(style)} vertex="1" parent={quoteattr(parent)}>'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        y += h + 40
        for child in node.get("nodes", []):
            emit(child, cid)

    for top in model.get("nodes", []):
        emit(top, "1")

    for i, rel in enumerate(model.get("relations", [])):
        if "implied" in (rel.get("tags") or []):
            continue  # derived relations are not the author's diagram
        label = escape(str(rel.get("description", "")))
        tech = rel.get("technology")
        if tech:
            label = f"{label}<br>[{escape(str(tech))}]" if label else f"[{escape(str(tech))}]"
        cells.append(
            f'<mxCell id={quoteattr(f"e{i}")} value={quoteattr(label)} style={quoteattr(_EDGE)} '
            f'edge="1" parent="1" source={quoteattr(rel["from"])} target={quoteattr(rel["to"])}>'
            f'<mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    name = escape(str(model.get("name", "architecture")))
    body = "".join(cells)
    return (
        f'<mxfile host="arb-mcp"><diagram name={quoteattr(name)}>'
        f'<mxGraphModel dx="800" dy="600" grid="1" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="850" pageHeight="1100" math="0" shadow="0">'
        f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root>'
        f'</mxGraphModel></diagram></mxfile>'
    )
