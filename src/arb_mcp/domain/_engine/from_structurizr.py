#!/usr/bin/env python3
"""Converts a Structurizr workspace into the meta-model.

The test of whether a new format is worth anything is not that it looks nice,
but that it absorbs what already exists. This converter reads Structurizr's DSL
and honestly reports what it could NOT bring over, instead of hiding it.

Structurizr's nine fixed types become a declared spec: they stop being the
language and become configuration.
"""
import json, re, sys
from pathlib import Path

TYPES = {
    "person": "person", "softwareSystem": "softwareSystem", "container": "container",
    "component": "component", "deploymentNode": "deploymentNode",
    "infrastructureNode": "infrastructureNode", "containerInstance": "containerInstance",
    "softwareSystemInstance": "systemInstance", "group": "group",
}
SPEC = {
    "nodeTypes": {
        "person": {"description": "A user of the system", "contains": []},
        "softwareSystem": {"description": "A software system", "contains": ["container"]},
        "container": {"description": "Something deployable", "contains": ["component"]},
        "component": {"description": "A part inside a container", "contains": []},
        "deploymentNode": {"description": "Where something runs"},
        "infrastructureNode": {"description": "Load balancer, firewall, DNS", "contains": []},
        "decision": {"description": "Decision record", "requires": ["status"], "contains": []},
    },
    "relationTypes": {
        "uses": {},
        "affects": {"description": "Ties a decision to what it decides", "from": ["decision"]},
    },
}

_ident = lambda s: re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:64] or "x"
_strings = lambda l: re.findall(r'"([^"]*)"', l)


def convert(text):
    lines = [l.rstrip() for l in text.splitlines()]
    lost = []
    nodes, relations, views = [], [], []
    stack = []          # open nodes
    section = None
    view_depth = 0
    root = {"name": "unnamed"}
    i = 0

    while i < len(lines):
        raw = lines[i]
        l = raw.strip()
        i += 1
        if not l or l.startswith("//") or l.startswith("#"):
            continue

        if re.match(r"^workspace\b", l):
            c = _strings(l)
            root = {"name": c[0] if c else "unnamed"}
            if len(c) > 1: root["description"] = c[1]
            continue
        if l in ("model {", "model{"): section = "model"; continue
        if l in ("views {", "views{"): section = "views"; continue

        if l == "}":
            if view_depth:
                view_depth -= 1
            elif stack:
                stack.pop()
            elif section:
                section = None
            continue

        if section == "views":
            m = re.match(r"^(systemContext|container|component|dynamic|deployment)\s+(\S+)\s+(.*)", l)
            if m:
                c = _strings(m.group(3))
                views.append({"id": _ident((c[0] if c else m.group(2))),
                              "title": c[0] if c else m.group(2),
                              "include": [{"inside": _ident(m.group(2))}]})
                if l.endswith("{"): view_depth += 1
            elif l.startswith(("autolayout", "include", "exclude")):
                pass   # layout is the visualizer's call, not the model's
            elif l.startswith(("styles", "element", "relationship", "theme", "branding")):
                if l.endswith("{"): view_depth += 1
                lost.append(f"style or theme: {l[:44]}")
            else:
                lost.append(f"in views, unrecognized: {l[:44]}")
            continue

        # ── element declaration ──
        m = re.match(r"^(?:(\w+)\s*=\s*)?(\w+)\s+(\".*)", l)
        if m and m.group(2) in TYPES:
            var, type_, rest = m.group(1), TYPES[m.group(2)], m.group(3)
            c = _strings(rest)
            n = {"id": _ident(var or (c[0] if c else type_)), "type": type_,
                 "name": c[0] if c else "?"}
            if len(c) > 1 and c[1]: n["description"] = c[1]
            if len(c) > 2 and c[2]: n["technology"] = c[2]
            if len(c) > 3: n["tags"] = [x.strip() for x in c[3].split(",")]
            (stack[-1].setdefault("nodes", []) if stack else nodes).append(n)
            if l.endswith("{"): stack.append(n)
            continue

        # ── relation ──
        m = re.match(r"^(\S+)\s*->\s*(\S+)\s*(.*)", l)
        if m:
            c = _strings(m.group(3))
            r = {"from": _ident(m.group(1)), "to": _ident(m.group(2)), "type": "uses"}
            if c and c[0]: r["description"] = c[0]
            if len(c) > 1 and c[1]: r["technology"] = c[1]
            relations.append(r)
            continue

        # ── properties inside an element ──
        m = re.match(r"^tags\s+(.*)", l)
        if m and stack:
            stack[-1].setdefault("tags", []).extend(x.strip() for x in _strings(m.group(1)))
            continue
        if re.match(r"^(description|technology|url|properties|perspectives)\b", l) and stack:
            lost.append(f"element property: {l[:40]}")
            continue
        if l.startswith("!"):
            lost.append(f"directive: {l[:40]}")
            continue
        if l not in ("{", "}"):
            lost.append(f"unrecognized: {l[:50]}")

    model = {"version": "1.0", **root, "spec": SPEC, "nodes": nodes}
    if relations: model["relations"] = relations
    if views: model["views"] = views
    return model, lost


if __name__ == "__main__":
    m, lost = convert(Path(sys.argv[1]).read_text())
    if "--report" in sys.argv:
        def count(ns):
            return sum(1 + count(n.get("nodes", [])) for n in ns)
        print(f"  nodes converted:   {count(m['nodes'])}")
        print(f"  relations:         {len(m.get('relations', []))}")
        print(f"  views:             {len(m.get('views', []))}")
        print(f"  NOT converted:     {len(lost)} constructs")
        for p in lost[:8]:
            print(f"      {p}")
    else:
        print(json.dumps(m, indent=1, ensure_ascii=False))
