"""Render profile: how ONE tool paints a model.

It is not part of the model and the model never names it: whoever invokes the
exporter chooses it. Two profiles over the same model must validate identically
and produce two different drawings — the test that keeps design out of the
architecture. Sizes here are drawio's own C4 palette (``Sidebar-C4.js`` in
jgraph/drawio): 240x120 for system, container and component, 200x180 for a
person, all ``resizable=0``. That is why a size never sits on a node type in
the schema: it would put one tool's palette into every tool's model.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Any

Size = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Grid:
    rank_gap: int = 80
    order_gap: int = 60
    # A container needs room BELOW for its own label: drawio draws a boundary's
    # name with verticalAlign=bottom, three lines tall. Without this reserve the
    # last child sits on top of it and the container goes unnamed, which is
    # exactly what the first exported file showed when opened.
    label_room: int = 70


@dataclass(frozen=True, slots=True)
class RenderProfile:
    name: str
    sizes: Mapping[str, Size]  # by node type
    default_size: Size
    grid: Grid
    boundary_size: Size

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RenderProfile:
        types = d.get("nodeTypes") or {}
        sizes = {k: _size(v.get("size")) for k, v in types.items() if v.get("size")}
        default = _size((d.get("defaults") or {}).get("size")) or (240, 120)
        g = d.get("grid") or {}
        return cls(
            name=str(d.get("profile", "")),
            sizes=MappingProxyType({k: v for k, v in sizes.items() if v}),
            default_size=default,
            grid=Grid(
                rank_gap=int(g.get("rankGap", 80)),
                order_gap=int(g.get("orderGap", 60)),
                label_room=int(g.get("labelRoom", 70)),
            ),
            boundary_size=sizes.get("boundary") or default,
        )

    @classmethod
    def load(cls, name: str) -> RenderProfile:
        """A profile shipped with the package: ``c4`` or ``generic``."""
        text = (files("arb_mcp.domain.specs") / f"{name}.render.json").read_text("utf-8")
        return cls.from_dict(json.loads(text))

    def size_of(self, node_type: str) -> Size:
        return self.sizes.get(node_type, self.default_size)


def _size(v: Any) -> Size | None:
    if not v:
        return None
    return int(v[0]), int(v[1])
