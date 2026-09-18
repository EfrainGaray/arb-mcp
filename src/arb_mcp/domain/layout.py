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


def _centre(placed: dict[str, Placed], spans: list[tuple[list[str], int]], widest: int) -> None:
    """Shift each rank so it is centred against the widest one.

    A lone node used to sit under the FIRST of the row above rather than in the
    middle of the picture, which sent every other edge across the diagram on its
    way past.
    """
    for row_ids, span in spans:
        shift = (widest - span) // 2
        if not shift:
            continue
        for nid in row_ids:
            q = placed[nid]
            placed[nid] = Placed(q.id, q.parent, q.x + shift, q.y, q.w, q.h, q.origin)


def _mirror(out: list[Placed], *, horizontal: bool, total: int) -> list[Placed]:
    """Reverse the reading order by mirroring along the axis the ranks advance on.

    That axis is x once the page has been turned and y otherwise. Flipping y for
    both mirrored the order *within* each rank and left the sequence alone, so
    "left" drew exactly what "right" drew.

    The mirror is taken inside the box that holds each level -- the parent's own
    size, or the whole diagram at the top -- and not against how far the children
    happened to reach, which drops the inset a container keeps around them and
    lands the last child hard on the boundary at 0.
    """
    caja = {p.id: (p.w if horizontal else p.h) for p in out}

    def espejo(p: Placed) -> Placed:
        dentro = total if p.parent is None else caja.get(p.parent, 0)
        if horizontal:
            return Placed(p.id, p.parent, dentro - p.x - p.w, p.y, p.w, p.h, p.origin)
        return Placed(p.id, p.parent, p.x, dentro - p.y - p.h, p.w, p.h, p.origin)

    return [espejo(p) for p in out]


def resolve(boxes: tuple[Box, ...], layout: Layout | None, grid: Grid) -> Resolved:
    """Place every box. Coordinates come out RELATIVE to the parent, which is
    how drawio reads a nested cell, so nesting maps one to one."""
    horizontal = layout is not None and layout.direction in ("right", "left")
    # Reading sideways is the same arithmetic on a turned page: every box is
    # laid out transposed and turned back at the end. Swapping only x and y
    # afterwards is not enough -- the step between ranks would then come from
    # the box's height while its width is what has to clear.
    work = (
        tuple(Box(b.id, b.parent, (b.size[1], b.size[0])) for b in boxes) if horizontal else boxes
    )
    cells, missing = _cells(work, layout)
    derived = set(missing)
    origin = (layout.origin or "manual") if layout else "derived"
    children: Mapping[str | None, list[Box]] = _group(work)
    placed: dict[str, Placed] = {}
    # A parent grows to fit its children: one gap across the rank, and room for
    # its own label along the reading axis. Transposed, the two swap over.
    room = grid.rank_gap // 2 + grid.label_room
    grow_w, grow_h = (room, grid.order_gap) if horizontal else (grid.order_gap, room)
    rank_gap = grid.edge_label_room if horizontal else grid.rank_gap

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
        spans: list[tuple[list[str], int]] = []  # the ids of each rank and its extent
        for rank in sorted(rows):
            x = x0
            row_h = 0
            row_ids: list[str] = []
            for b in sorted(rows[rank], key=lambda b: cells[b.id].order):
                w, h = b.size
                iw, ih = place(b.id)
                if iw or ih:  # a node with children must fit them: grow
                    w = max(w, iw + grow_w)
                    h = max(h, ih + grow_h)
                placed[b.id] = Placed(
                    b.id, parent, x, y, w, h, "derived" if b.id in derived else origin
                )
                row_ids.append(b.id)
                x += w + grid.order_gap
                row_h = max(row_h, h)
            span = x - x0 - grid.order_gap
            spans.append((row_ids, span))
            total_w = max(total_w, span)
            y += row_h + rank_gap
        _centre(placed, spans, total_w)
        total_h = y - (grid.rank_gap // 2 if parent is not None else 0) - rank_gap
        return total_w, total_h

    w, h = place(None)
    out = [placed[b.id] for b in work if b.id in placed]
    if horizontal:  # turn the page back: coordinates AND sizes
        out = [Placed(p.id, p.parent, p.y, p.x, p.h, p.w, p.origin) for p in out]
        w, h = h, w
    if layout and layout.direction in ("up", "left"):
        out = _mirror(out, horizontal=horizontal, total=w if horizontal else h)
    return Resolved(tuple(out), w, h, tuple(missing))


def _group(boxes: tuple[Box, ...]) -> dict[str | None, list[Box]]:
    out: dict[str | None, list[Box]] = {}
    for b in boxes:
        out.setdefault(b.parent, []).append(b)
    return out
