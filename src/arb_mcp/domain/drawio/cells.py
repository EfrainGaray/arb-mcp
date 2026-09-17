"""Low-level mxGraph XML emission: one function per drawio element type.

These are the only functions that touch the XML wire format.  Everything
above them (scoping, layout, profile) works with domain objects; everything
below (styles) is just strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from ..model import Node, Relation
from .styles import C4_LABEL_PLAIN, C4_LABEL_TECH, C4_TYPE_LABEL, EDGE


@dataclass(frozen=True, slots=True)
class Diagram:
    """One standalone drawio file: a C4 level (or a flat notation) over a scope."""

    level: str
    scope: str
    name: str
    xml: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "scope": self.scope, "name": self.name, "xml": self.xml}


def label(node: Node) -> str:
    """Human-readable HTML label for a node (name + optional technology + description)."""
    parts = [f"<b>{escape(node.name)}</b>"]
    if node.technology:
        parts.append(f"[{escape(node.technology)}]")
    if node.description:
        parts.append(escape(node.description))
    return "<br>".join(parts)


def c4_vertex(node: Node, style: str, x: int, y: int, w: int, h: int, parent: str = "1") -> str:
    """A native drawio C4 element: an <object> with c4* attributes and a
    placeholder label, exactly as drawio's own C4 shape library builds it — so
    it opens as a real C4 card (name, [Type: Technology], description), not a
    plain coloured box."""
    tmpl = C4_LABEL_TECH if node.type in ("container", "component") else C4_LABEL_PLAIN
    attrs = [
        f"label={quoteattr(tmpl)}",
        'placeholders="1"',
        f"c4Name={quoteattr(node.name)}",
        f"c4Type={quoteattr(C4_TYPE_LABEL.get(node.type, node.type))}",
    ]
    if node.technology:
        attrs.append(f"c4Technology={quoteattr(node.technology)}")
    attrs.append(f"c4Description={quoteattr(node.description)}")
    attrs.append(f"id={quoteattr(node.id)}")
    return (
        f"<object {' '.join(attrs)}>"
        f'<mxCell style={quoteattr(style)} vertex="1" parent={quoteattr(parent)}>'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f"</mxCell></object>"
    )


def vertex(
    cid: str, label_text: str, style: str, x: int, y: int, w: int, h: int, parent: str = "1"
) -> str:
    """A plain mxCell vertex (used for UML/flat views and boundaries)."""
    return (
        f"<mxCell id={quoteattr(cid)} value={quoteattr(label_text)} style={quoteattr(style)} "
        f'vertex="1" parent={quoteattr(parent)}>'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def mxfile(name: str, cells: list[str]) -> str:
    """Wrap cells in a complete standalone drawio mxfile XML string."""
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
    lbl = escape(rel.description)
    if rel.technology:
        tech = f"[{escape(rel.technology)}]"
        lbl = f"{lbl}<br>{tech}" if lbl else tech
    return lbl


def _edge_cell(eid: str, lbl: str, src: str, dst: str) -> str:
    return (
        f"<mxCell id={quoteattr(eid)} value={quoteattr(lbl)} style={quoteattr(EDGE)} "
        f'edge="1" parent="1" source={quoteattr(src)} target={quoteattr(dst)}>'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def edges(pairs: list[tuple[str, str, Relation]]) -> list[str]:
    """Convert (source, target, relation) pairs to edge cell XML strings."""
    return [_edge_cell(f":e{i}", _rel_label(rel), a, b) for i, (a, b, rel) in enumerate(pairs)]
