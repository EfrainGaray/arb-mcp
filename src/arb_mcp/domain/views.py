"""Evaluate a view's queries against the model: WHO is in the picture.

A view is a query, not a list, so it stays correct as the model grows. This is
the one place the five query shapes mean something: ``*`` is every element,
``type`` and ``tag`` select by declaration, ``inside`` walks down from a node to
a depth, ``neighbors`` walks the relations out from a node a number of hops
(both directions — a picture of what surrounds X must show what calls X too).
``exclude`` is applied after ``include``. Elements come back in model order so
two evaluations, and two implementations, agree on the list.
"""

from __future__ import annotations

from .model import All, ByTag, ByType, Inside, Model, Neighbors, Node, Query, View


def _inside(model: Model, node_id: str, depth: int) -> set[str]:
    root = model.get(node_id)
    if root is None:
        return set()
    out: set[str] = set()
    frontier = [(c, 1) for c in root.nodes]
    while frontier:
        n, d = frontier.pop()
        out.add(n.id)
        if d < depth:
            frontier.extend((c, d + 1) for c in n.nodes)
    return out


def _neighbors(model: Model, node_id: str, hops: int) -> set[str]:
    if node_id not in model:
        return set()
    adjacent: dict[str, set[str]] = {}
    for r in model.relations:
        adjacent.setdefault(r.source, set()).add(r.target)
        adjacent.setdefault(r.target, set()).add(r.source)
    seen = {node_id}
    frontier = {node_id}
    for _ in range(hops):
        frontier = {b for a in frontier for b in adjacent.get(a, ())} - seen
        seen |= frontier
    return seen


def _select(model: Model, q: Query) -> set[str]:
    match q:
        case All():
            return {n.id for n in model.walk()}
        case ByType(t):
            return {n.id for n in model.walk() if n.type == t}
        case ByTag(t):
            return {n.id for n in model.walk() if t in n.tags}
        case Inside(node, depth):
            return _inside(model, node, depth)
        case Neighbors(node, hops):
            return _neighbors(model, node, hops)


def members(model: Model, view: View) -> tuple[Node, ...]:
    """The elements a view shows, in model order."""
    chosen: set[str] = set()
    for q in view.include:
        chosen |= _select(model, q)
    for q in view.exclude:
        chosen -= _select(model, q)
    return tuple(n for n in model.walk() if n.id in chosen)


def named_nodes(q: Query) -> tuple[str, ...]:
    """The node ids a query refers to, for integrity checks."""
    match q:
        case Inside(node, _) | Neighbors(node, _):
            return (node,)
        case _:
            return ()
