"""Export a canonical model to drawio (mxGraph) XML as separate C4 views.

Public surface (unchanged from when this was a single module):
- ``Diagram``        — one standalone drawio file
- ``to_views()``    — dispatch by notation: C4 → multiple C1/C2/C3 diagrams,
                      anything else → one flat diagram
- ``to_c4_views()`` — always the C4 path (C1 + one C2/C3 per focus node)

Consumers of ``from arb_mcp.domain import drawio`` see exactly the same API
they did before the package split.
"""

from __future__ import annotations

from ..model import Model
from ..render import RenderProfile
from .c4 import to_c4_views
from .cells import Diagram
from .flat import _view_flat


def to_views(model: Model, profile: RenderProfile | None = None) -> list[Diagram]:
    """Dispatch by notation: C4 models get the separate C1/C2/C3 views; any
    other spec (UML use cases, etc.) gets a single flat diagram."""
    if model.is_c4:
        return to_c4_views(model, profile)
    return [_view_flat(model, profile or RenderProfile.load("generic"))]


__all__ = ["Diagram", "to_c4_views", "to_views"]
