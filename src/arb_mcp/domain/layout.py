"""Turns cells into pixels: the only place where a coordinate is ever invented.

The model states ``rank``/``order`` — reading depth and position within it —
and the render profile states the size. Everything else is arithmetic, and that
is the point: with the same input this returns the same rectangles in Java,
Python or Go, because there is no solver to disagree about. Structurizr's own
layout is a call to Dagre, whose output changes with its version; that is what
makes a diagram move when nothing in the model moved.

A node the view shows and the layout does not mention is NOT an error. It is
placed after the last authored rank of its parent, one per rank in declaration
order (a column), and marked ``derived`` so a reader can tell an authored
position from a filled-in one. Ported from the DSL project's ``resolve_layout``;
the measured reason for cells over pixels is in the schema's own description.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model import Layout, Placement
from .render import Grid, Size


@dataclass(frozen=True, slots=True)
class Box:
    """A node to place: who its parent is in THIS view and its own size."""

    id: str
    parent: str | None
    size: Size


@dataclass(frozen=True, slots=True)
class Placed:
    id: str
    parent: str | None
    x: int  # relative to the parent's box
    y: int
    w: int
    h: int
    origin: str  # "manual" | "imported" | "derived"


@dataclass(frozen=True, slots=True)
class Resolved:
    nodes: tuple[Placed, ...]
    width: int
    height: int
    derived: tuple[str, ...]  # ids the layout did not mention

    def get(self, node_id: str) -> Placed | None:
        return next((p for p in self.nodes if p.id == node_id), None)


def _cells(boxes: tuple[Box, ...], layout: Layout | None) -> tuple[dict[str, Placement], list[str]]:
    cells: dict[str, Placement] = {p.node: p for p in layout.placements} if layout else {}
    missing = [b.id for b in boxes if b.id not in cells]
    by_parent: dict[str | None, list[Box]] = {}
    for b in boxes:
        by_parent.setdefault(b.parent, []).append(b)
    for group in by_parent.values():
        used = [cells[b.id].rank for b in group if b.id in cells]
        nxt = (max(used) + 1) if used else 0
        for i, b in enumerate(b for b in group if b.id not in cells):
            cells[b.id] = Placement(node=b.id, rank=nxt + i, order=0)
    return cells, missing


def resolve(boxes: tuple[Box, ...], layout: Layout | None, grid: Grid) -> Resolved:
    """Place every box. Coordinates come out RELATIVE to the parent, which is
    how drawio reads a nested cell, so nesting maps one to one."""
    cells, missing = _cells(boxes, layout)
    derived = set(missing)
    origin = (layout.origin or "manual") if layout else "derived"
    children: Mapping[str | None, list[Box]] = _group(boxes)
    placed: dict[str, Placed] = {}

    def place(parent: str | None) -> Size:
        """Place one level in the parent's own coordinates; return the box it needed."""
        group = children.get(parent, [])
        if not group:
            return 0, 0
        rows: dict[int, list[Box]] = {}
        for b in group:
            rows.setdefault(cells[b.id].rank, []).append(b)
        total_w = total_h = 0
        y = grid.rank_gap // 2 if parent is not None else 0
        x0 = grid.order_gap // 2 if parent is not None else 0
        for rank in sorted(rows):
            x = x0
            row_h = 0
            for b in sorted(rows[rank], key=lambda b: cells[b.id].order):
                w, h = b.size
                iw, ih = place(b.id)
                if iw or ih:  # a node with children must fit them: grow
                    w = max(w, iw + grid.order_gap)
                    h = max(h, ih + grid.rank_gap // 2 + grid.label_room)
                placed[b.id] = Placed(
                    b.id, parent, x, y, w, h, "derived" if b.id in derived else origin
                )
                x += w + grid.order_gap
                row_h = max(row_h, h)
            total_w = max(total_w, x - x0 - grid.order_gap)
            y += row_h + grid.rank_gap
        total_h = y - (grid.rank_gap // 2 if parent is not None else 0) - grid.rank_gap
        return total_w, total_h

    w, h = place(None)
    out = [placed[b.id] for b in boxes if b.id in placed]
    if layout and layout.direction in ("right", "left"):
        out = [Placed(p.id, p.parent, p.y, p.x, p.w, p.h, p.origin) for p in out]
        w, h = h, w
    if layout and layout.direction in ("up", "left"):
        extent = {p.parent: 0 for p in out}
        for p in out:
            extent[p.parent] = max(extent[p.parent], p.y + p.h)
        out = [
            Placed(p.id, p.parent, p.x, extent[p.parent] - p.y - p.h, p.w, p.h, p.origin)
            for p in out
        ]
    return Resolved(tuple(out), w, h, tuple(missing))


def _group(boxes: tuple[Box, ...]) -> dict[str | None, list[Box]]:
    out: dict[str | None, list[Box]] = {}
    for b in boxes:
        out.setdefault(b.parent, []).append(b)
    return out
