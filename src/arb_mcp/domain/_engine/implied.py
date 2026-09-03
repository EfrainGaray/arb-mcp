#!/usr/bin/env python3
"""Implied relations: a declared transformation, not a hardwired rule.

Structurizr creates them always and silently: if a component talks to another,
it infers that their containers and systems talk too. It is useful, and it is
why its export carries 20 relations where the text declares 13.

Here it is a named transformation you ask for. The model keeps what was
written; this derives the rest. Derived ones are tagged "implied" so nobody
mistakes them for what someone actually stated.

The algorithm replicates Structurizr's exactly
(CreateImpliedRelationshipsUnlessAnyRelationshipExistsStrategy):

    for each ancestor of the source (source included):
        for each ancestor of the destination (destination included):
            if they are not the same and neither is an ancestor of the other:
                if the source has no outgoing relation to the destination yet:
                    create the implied relation
"""

# A person is never counted as parent or child. Without this rule the numbers
# do not match the official parser, and finding it took a full differential run.
PERSON_TYPES = {"person"}


def _index(nodes, parent=None, by_id=None, parents=None):
    by_id = {} if by_id is None else by_id
    parents = {} if parents is None else parents
    for n in nodes:
        by_id[n["id"]] = n
        parents[n["id"]] = parent
        _index(n.get("nodes", []), n["id"], by_id, parents)
    return by_id, parents


def _chain(ident, parents):
    """The element and all its ancestors, innermost first."""
    out = []
    while ident is not None:
        out.append(ident)
        ident = parents.get(ident)
    return out


def _is_ancestor(a, b, parents, by_id):
    """Is a an ancestor of b? People never count as parent nor child."""
    if by_id.get(a, {}).get("type") in PERSON_TYPES or by_id.get(b, {}).get("type") in PERSON_TYPES:
        return False
    p = parents.get(b)
    while p is not None:
        if p == a:
            return True
        p = parents.get(p)
    return False


def derive(model):
    by_id, parents = _index(model["nodes"])
    declared = list(model.get("relations", []))
    outgoing = {(r["from"], r["to"]) for r in declared}
    fresh = []

    for r in declared:
        for src in _chain(r["from"], parents):
            for dst in _chain(r["to"], parents):
                if src == dst:
                    continue
                if _is_ancestor(src, dst, parents, by_id) or _is_ancestor(dst, src, parents, by_id):
                    continue
                if (src, dst) in outgoing:
                    continue
                outgoing.add((src, dst))
                d = {"from": src, "to": dst, "tags": ["implied"]}
                for k in ("type", "description", "technology"):
                    if k in r:
                        d[k] = r[k]
                fresh.append(d)

    if fresh:
        model = dict(model)
        model["relations"] = declared + fresh
    return model, len(fresh)
