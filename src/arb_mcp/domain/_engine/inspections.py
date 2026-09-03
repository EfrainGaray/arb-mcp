#!/usr/bin/env python3
"""Inspections over the meta-model: the architecture linter.

Structurizr ships 44 rules hardwired to its types: one demanding documentation
on a "softwareSystem", another decisions, another technology on relations.
They work because its nine types are fixed.

Here types are declared, so the rules cannot name them. They lean on what the
spec SAYS about each type: if a type declares `requires`, that is a rule; if a
type can contain others, documentation can be demanded once it does. The spec
stops being decorative and becomes the contract that gets checked.

Violations are reported in the same shape as the official CLI so both can be
compared line by line: SEVERITY | rule.kind | message
"""
ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


def _walk(nodes, parent=""):
    for n in nodes:
        path = f"{parent}.{n['name']}" if parent else n["name"]
        yield n, path
        yield from _walk(n.get("nodes", []), path)


def inspect(model):
    v = []
    spec = model["spec"]
    types = spec["nodeTypes"]
    nodes = list(_walk(model["nodes"]))
    by_id = {n["id"]: (n, p) for n, p in nodes}

    # ── 1. what the spec declares mandatory ──
    for n, path in nodes:
        for field in types.get(n["type"], {}).get("requires", []):
            if not (n.get(field) or (n.get("properties") or {}).get(field)):
                v.append((ERROR, f"model.{n['type']}.{field}",
                          f'The {n["type"]} "{path}" does not declare {field}, which its type requires.'))

    # ── 2. a node with children should be documented ──
    for n, path in nodes:
        if n.get("nodes") and not n.get("docs"):
            v.append((ERROR, f"model.{n['type']}.documentation",
                      f'The {n["type"]} "{path}" holds {len(n["nodes"])} elements inside, but is not documented.'))

    # ── 3. a node with children should be backed by some decision ──
    decision_types = [t for t in types if "decision" in t.lower()]
    if decision_types:
        decided = set()
        for r in model.get("relations", []):
            if by_id.get(r["from"], ({}, ""))[0].get("type") in decision_types:
                decided.add(r["to"])
        for n, path in nodes:
            if n.get("nodes") and n["id"] not in decided:
                v.append((ERROR, f"model.{n['type']}.decisions",
                          f'The {n["type"]} "{path}" holds elements inside, but no decision backs it.'))

    # ── 4. relations with no technology ──
    # DELIBERATE DIVERGENCE from Structurizr, measured in the cross-check: the
    # official inspects derived relations too, so it reports TWO errors for a
    # single missing technology — one on the relation someone wrote and one on
    # the relation the machine inferred. The second cannot be fixed where it
    # appears. Here only what a person wrote is held against them.
    for r in model.get("relations", []):
        if "implied" in (r.get("tags") or []):
            continue
        if not r.get("technology"):
            a = by_id.get(r["from"], ({}, r["from"]))[1]
            b = by_id.get(r["to"], ({}, r["to"]))[1]
            v.append((ERROR, "model.relation.technology",
                      f'The relation between "{a}" and "{b}" declares no technology.'))

    # ── 5. elements with no description ──
    for n, path in nodes:
        if not n.get("description"):
            v.append((WARNING, f"model.{n['type']}.description",
                      f'The {n["type"]} "{path}" has no description.'))

    # ── 6. disconnected elements ──
    touched = set()
    for r in model.get("relations", []):
        touched.add(r["from"]); touched.add(r["to"])
    for n, path in nodes:
        if n["id"] not in touched and not n.get("nodes"):
            v.append((WARNING, "model.element.disconnected",
                      f'The element "{path}" relates to nothing.'))

    # ── 7. the model should declare its scope ──
    # Equivalent to the official workspace.scope: a field of its own with
    # closed values, NOT the description. Confusing the two was an error in
    # the first cross-check, and it compared two different things.
    if model.get("scope", "undefined") == "undefined":
        v.append((ERROR, "model.scope",
                  'The model does not declare its scope. "landscape" or "system" is recommended.'))

    return v


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    m = json.loads(Path(sys.argv[1]).read_text())
    for sev, kind, msg in inspect(m):
        print(f"{sev:7}| {kind:36}| {msg}")
