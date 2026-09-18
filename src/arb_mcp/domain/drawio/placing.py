"""Placement helpers: mapping authored layout queries to resolved geometry.

Shared by the C4 per-level builders and the flat-view builder; kept in a
neutral module so neither depends on the other.
"""

from __future__ import annotations

from ..layout import Box, Resolved
from ..layout import resolve as _resolve
from ..model import All, ByTag, ByType, Inside, Layout, Model
from ..render import RenderProfile


def layout_for(model: Model, focus: str | None) -> Layout | None:
    """The authored layout of the view over ``focus`` (``None`` = the landscape).

    The landscape takes the geometry of any view that does not zoom into a node:
    a context view is free to select its members with ``*`` or by type, and both
    describe the same picture. Recognising only ``*`` dropped the layout of a
    view that listed its types -- silently, so the model was right and the
    diagram came out as a single column.
    """
    for v in model.views:
        if v.layout is None:
            continue
        adentro = [q for q in v.include if isinstance(q, Inside)]
        if focus is None:
            if not adentro and any(isinstance(q, All | ByType | ByTag) for q in v.include):
                return v.layout
            continue
        if any(q.node == focus for q in adentro):
            return v.layout
    return None


def place(boxes: list[Box], layout: Layout | None, profile: RenderProfile) -> Resolved:
    return _resolve(tuple(boxes), layout, profile.grid)


def cell_of(placed: Resolved, node_id: str) -> tuple[int, int, int, int, str]:
    """x, y, w, h and the drawio parent id of a placed node."""
    p = placed.get(node_id)
    if p is None:
        return 0, 0, 0, 0, "1"
    return p.x, p.y, p.w, p.h, p.parent or "1"
