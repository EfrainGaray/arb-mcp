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

from .c4 import to_c4_views
from .cells import Diagram
from .flat import to_views

__all__ = ["Diagram", "to_c4_views", "to_views"]
