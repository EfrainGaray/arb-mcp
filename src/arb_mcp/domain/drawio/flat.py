"""Flat diagram for non-C4 notations (UML use-case, deployment, …).

Every node is drawn as itself; containers nest their children; relations are
edges.  No lifting or scoping — the full model appears in one canvas.
"""

from __future__ import annotations

from ..c4_views import resolved_edges
from ..layout import Box
from ..model import Model
from ..render import RenderProfile
from .cells import Diagram, edges, label, mxfile, vertex
from .placing import cell_of, layout_for, place
from .styles import UML_BOUNDARY, UML_FALLBACK, UML_STYLE


def _flat_level(model: Model) -> str:
    t = model.spec.node_types
    if "actor" in t or "useCase" in t:
        return "UML"
    if "deploymentNode" in t:
        return "Deployment"
    return "Diagram"


def _view_flat(model: Model, profile: RenderProfile) -> Diagram:
    """A single diagram for any non-C4 notation: every element drawn as itself,
    containers nesting their children to arbitrary depth."""
    emitted = {n.id for n in model.walk()}

    def resolve_end(nid: str) -> str | None:
        return model.lift_to(nid, emitted)

    boxes = [Box(n.id, model.parent_of(n.id), profile.size_of(n.type)) for n in model.walk()]
    placed = place(boxes, layout_for(model, None), profile)
    cells: list[str] = []
    for n in model.walk():
        x, y, w, h, parent = cell_of(placed, n.id)
        style = UML_BOUNDARY if n.nodes else UML_STYLE.get(n.type, UML_FALLBACK)
        cells.append(vertex(n.id, label(n), style, x, y, w, h, parent))
    cells += edges(resolved_edges(model, resolve_end))
    lvl = _flat_level(model)
    return Diagram(
        level=lvl,
        scope=model.scope or "diagram",
        name=f"{model.name or 'Model'} \N{EM DASH} {lvl}",
        xml=mxfile(lvl, cells),
    )
