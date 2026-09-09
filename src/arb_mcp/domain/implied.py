"""Implied relations: a declared transformation, not a hardwired rule.

Structurizr creates them always and silently: if a component talks to another,
it infers that their containers and systems talk too. It is useful, and it is
why its export carries 20 relations where the text declares 13.

Here it is a named transformation you ask for. The model keeps what was
written; this derives the rest. Derived ones are tagged ``implied`` so nobody
mistakes them for what someone actually stated.

The algorithm replicates Structurizr's exactly
(``CreateImpliedRelationshipsUnlessAnyRelationshipExistsStrategy``)::

    for each ancestor of the source (source included):
        for each ancestor of the destination (destination included):
            if they are not the same and neither is an ancestor of the other:
                if the source has no outgoing relation to the destination yet:
                    create the implied relation
"""

from __future__ import annotations

from dataclasses import replace

from .model import Model, Relation

# A person is never counted as parent or child. Without this rule the numbers
# do not match the official parser, and finding it took a full differential run.
PERSON_TYPES = frozenset({"person"})


def _chain(model: Model, node_id: str) -> list[str]:
    """The element and all its ancestors, innermost first."""
    out: list[str] = []
    cur: str | None = node_id
    while cur is not None:
        out.append(cur)
        cur = model.parent_of(cur)
    return out


def _is_person(model: Model, node_id: str) -> bool:
    node = model.get(node_id)
    return node is not None and node.type in PERSON_TYPES


def _is_ancestor(model: Model, a: str, b: str) -> bool:
    """Is ``a`` an ancestor of ``b``? People never count as parent nor child."""
    if _is_person(model, a) or _is_person(model, b):
        return False
    p = model.parent_of(b)
    while p is not None:
        if p == a:
            return True
        p = model.parent_of(p)
    return False


def derive(model: Model) -> tuple[Model, int]:
    """Return the model with its implied relations appended, and how many were added."""
    outgoing = {(r.source, r.target) for r in model.relations}
    fresh: list[Relation] = []
    for r in model.relations:
        for src in _chain(model, r.source):
            for dst in _chain(model, r.target):
                if src == dst or (src, dst) in outgoing:
                    continue
                if _is_ancestor(model, src, dst) or _is_ancestor(model, dst, src):
                    continue
                outgoing.add((src, dst))
                fresh.append(
                    Relation(
                        source=src,
                        target=dst,
                        type=r.type,
                        description=r.description,
                        technology=r.technology,
                        tags=("implied",),
                    )
                )
    if not fresh:
        return model, 0
    return replace(model, relations=model.relations + tuple(fresh)), len(fresh)
