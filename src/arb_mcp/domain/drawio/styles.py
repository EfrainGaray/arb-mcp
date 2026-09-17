"""Style strings verbatim from drawio's mxgraph.c4 stencil (Sidebar-C4.js).

These are module-level constants that cross package-internal boundaries, so
they carry no leading underscore.  The names mirror their semantic roles, not
the drawio internal IDs.
"""

from __future__ import annotations

# Verbatim from drawio's mxgraph.c4 stencil (Sidebar-C4.js).
STYLE: dict[str, str] = {
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
EXTERNAL = (
    "rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor=#8C8496;"
    "fontColor=#ffffff;align=center;arcSize=10;strokeColor=#736782;metaEdit=1;resizable=0;"
)

# The in-focus element (system in C2, container in C3): a dashed boundary.
BOUNDARY = (
    "rounded=1;fontSize=11;whiteSpace=wrap;html=1;dashed=1;arcSize=20;fillColor=none;"
    "strokeColor=#666666;fontColor=#333333;labelBackgroundColor=none;align=left;"
    "verticalAlign=bottom;labelBorderColor=none;spacingTop=0;spacing=10;dashPattern=8 4;"
    "metaEdit=1;rotatable=0;perimeter=rectanglePerimeter;allowArrows=0;connectable=0;"
    "expand=0;recursiveResize=0;absoluteArcSize=1;container=1;collapsible=0;"
)

EDGE = (
    "endArrow=blockThin;html=1;fontSize=10;fontColor=#404040;strokeWidth=1;endFill=1;"
    "strokeColor=#828282;elbow=vertical;metaEdit=1;endSize=14;startSize=14;jumpStyle=arc;"
    "jumpSize=16;rounded=0;edgeStyle=orthogonalEdgeStyle;"
)

# UML and generic shapes, standard drawio primitives.
UML_STYLE: dict[str, str] = {
    "actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
    "outlineConnect=0;",
    "useCase": "ellipse;whiteSpace=wrap;html=1;",
}
UML_FALLBACK = "rounded=0;whiteSpace=wrap;html=1;"
UML_BOUNDARY = (
    "rounded=0;whiteSpace=wrap;html=1;dashed=1;verticalAlign=top;"
    "align=center;fillColor=none;strokeColor=#666666;container=1;collapsible=0;"
)

# C4 placeholder-label metadata used by _c4_vertex.
C4_TYPE_LABEL: dict[str, str] = {
    "person": "Person",
    "softwareSystem": "Software System",
    "container": "Container",
    "component": "Component",
}
C4_LABEL_PLAIN = (
    '<font style="font-size: 16px"><b>%c4Name%</b></font>'
    '<div>[%c4Type%]</div><br><div><font style="font-size: 11px">'
    '<font color="#cccccc">%c4Description%</font></div>'
)
C4_LABEL_TECH = (
    '<font style="font-size: 16px"><b>%c4Name%</b></font>'
    '<div>[%c4Type%: %c4Technology%]</div><br><div><font style="font-size: 11px">'
    '<font color="#E6E6E6">%c4Description%</font></div>'
)
