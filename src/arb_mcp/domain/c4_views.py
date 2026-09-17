"""Notation-neutral C4 scoping: which elements appear in each view and how
edges resolve across boundaries.

This module answers "what" — which model elements are in scope, which are
external, and how relations are lifted to visible endpoints — without
touching pixels, profiles, or XML syntax.  Both the drawio package and the
mermaid module consume it, so the two exporters cannot silently diverge.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .model import Model, Node, Relation


@dataclass(frozen=True, slots=True)
class Edge:
    """A relation visible at a specific C4 level: endpoints are the *visible*
    cell ids at that level (lifted to their representative), not the raw
    relation endpoints."""

    source: str  # visible cell id at this level
    target: str
    relation: Relation  # the written relation it represents


@dataclass(frozen=True, slots=True)
class C4View:
    """The scope of one C4 diagram: what is inside the focus, what is outside
    but reachable, and how the written relations resolve to visible edges.

    Notation-neutral: no pixel, no profile, no XML.  The drawio package and
    the mermaid module both consume this; they cannot drift from each other
    because they share the same scoping logic.
    """

    level: str  # "C1" | "C2" | "C3"
    focus: Node | None  # None for C1 (the landscape has no single focus)
    inside: tuple[Node, ...]  # drawn within the focus boundary (or all tops for C1)
    externals: tuple[Node, ...]  # nodes reached by an edge that are outside the focus
    edges: tuple[Edge, ...]
    name: str  # human-readable diagram title; identical to drawio's Diagram.name

    @property
    def scope(self) -> str:
        """The canonical scope identifier: 'system-landscape' for C1, the
        focus node id for C2/C3 — same value as Diagram.scope in drawio."""
        return "system-landscape" if self.focus is None else self.focus.id


# ─────────────────────────── internal helpers ───────────────────────────
def _resolved_edges(
    model: Model, resolve: Callable[[str], str | None]
) -> list[tuple[str, str, Relation]]:
    """Every written relation collapsed to its visible endpoints, deduped by
    pair.  Both exporters call this through c4_views so they cannot diverge."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, Relation]] = []
    for rel in model.written_relations():
        a, b = resolve(rel.source), resolve(rel.target)
        if a is None or b is None or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append((a, b, rel))
    return out


def _ext_nodes(
    model: Model,
    pairs: list[tuple[str, str, Relation]],
    focus: str,
    inside: set[str],
) -> list[Node]:
    """Elements outside the focus that an edge actually reaches, in first-seen order."""
    seen: dict[str, Node] = {}
    for a, b, _ in pairs:
        for end in (a, b):
            if end != focus and end not in inside and end not in seen:
                node = model.get(end)
                if node is not None:
                    seen[end] = node
    return list(seen.values())


# ─────────────────────────── public API ───────────────────────────
def context(model: Model) -> C4View:
    """C1 System Context: persons and top-level software systems; edges lifted
    to their top-level representative."""
    tops = [n for n in model.nodes if n.type in ("person", "softwareSystem")]
    top_ids = {n.id for n in tops}

    def resolve_end(nid: str) -> str | None:
        t = model.top_of(nid)
        return t if t in top_ids else None

    pairs = _resolved_edges(model, resolve_end)
    return C4View(
        level="C1",
        focus=None,
        inside=tuple(tops),
        externals=(),  # C1 has no externals — every element IS a top-level node
        edges=tuple(Edge(a, b, rel) for a, b, rel in pairs),
        name=f"{model.name or 'Architecture'} \N{EM DASH} C1 System Context",
    )


def containers(model: Model, system: Node) -> C4View:
    """C2 Container diagram: containers inside the system; externals are every
    other element reached by an edge."""
    sid = system.id
    conts = system.children_of_type("container")
    container_ids = {c.id for c in conts}

    def resolve_end(nid: str) -> str | None:
        if nid not in model:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = model.lift_to(nid, container_ids)
        return inside if inside is not None else model.top_of(nid)

    pairs = _resolved_edges(model, resolve_end)
    ext_nodes = _ext_nodes(model, pairs, sid, container_ids)
    return C4View(
        level="C2",
        focus=system,
        inside=tuple(conts),
        externals=tuple(ext_nodes),
        edges=tuple(Edge(a, b, rel) for a, b, rel in pairs),
        name=f"{system.name} \N{EM DASH} C2 Containers",
    )


def components(model: Model, container: Node) -> C4View:
    """C3 Component diagram: components inside the container; sibling
    containers, systems and persons appear as externals when reached by an edge."""
    cid = container.id
    comps = container.children_of_type("component")
    comp_ids = {c.id for c in comps}

    def resolve_end(nid: str) -> str | None:
        if nid not in model:
            return None  # dangling endpoint: the linter blocks it; never crash here
        inside = model.lift_to(nid, comp_ids)
        if inside is not None:
            return inside
        # a sibling container, a top-level system/person, or the focus container
        # itself (its boundary, drawn with id=cid) represents the endpoint
        cur: str | None = nid
        while cur is not None:
            node = model.get(cur)
            if node is None:
                return None
            p = model.parent_of(cur)
            if p is None or node.type in ("container", "softwareSystem", "person"):
                return cur
            cur = p
        return None

    pairs = _resolved_edges(model, resolve_end)
    ext_nodes = _ext_nodes(model, pairs, cid, comp_ids)
    return C4View(
        level="C3",
        focus=container,
        inside=tuple(comps),
        externals=tuple(ext_nodes),
        edges=tuple(Edge(a, b, rel) for a, b, rel in pairs),
        name=f"{container.name} \N{EM DASH} C3 Components",
    )


def c4_views(model: Model) -> list[C4View]:
    """Enumerate all C4 views in the canonical order: one C1, one C2 per
    software system that has containers, one C3 per container that has
    components.  Same ordering as drawio.to_c4_views — the two functions share
    this enumeration so they cannot diverge."""
    views: list[C4View] = [context(model)]
    views.extend(
        containers(model, n)
        for n in model.nodes
        if n.type == "softwareSystem" and n.children_of_type("container")
    )
    views.extend(
        components(model, n)
        for n in model.walk()
        if n.type == "container" and n.children_of_type("component")
    )
    return views
