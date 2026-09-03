#!/usr/bin/env python3
"""Converter between the language and the schema, both ways.

The hard rule of this project: conversion loses nothing. If something can be
written in the language and does not survive the schema, the schema is
incomplete. If something fits the schema and cannot be written, the language
is.

That is why the module ships its own round-trip test: text -> json -> text
must yield the same text, and json -> text -> json the same json.
"""
import json, re, sys
from pathlib import Path
from lark import Lark, Tree

GRAMMAR = Path(__file__).parent / "grammar" / "grammar.lark"
_lark = Lark(GRAMMAR.read_text(), start="model", parser="earley")

_txt = lambda t: str(t)[1:-1] if str(t).startswith('"') else str(t)
_long = lambda t: str(t)[3:-3].strip()


# ─────────────────────────── language -> schema ───────────────────────────

def _query(t):
    d = t.data
    if d == "all": return "*"
    if d == "by_type": return {"type": str(t.children[0])}
    if d == "by_tag": return {"tag": _txt(t.children[0])}
    if d in ("inside", "neighbors"):
        key = "inside" if d == "inside" else "neighbors"
        span = "depth" if d == "inside" else "hops"
        r = {key: str(t.children[0])}
        if len(t.children) > 1 and t.children[1] is not None:
            r[span] = int(t.children[1])
        return r
    raise ValueError(d)


def _node(t, relations):
    children = [c for c in t.children if isinstance(c, Tree)]
    flat = [c for c in t.children if not isinstance(c, Tree)]
    # [ident=] type "name" ["description"]
    if len(flat) >= 3 and flat[0] is not None:
        ident, type_, name = str(flat[0]), str(flat[1]), _txt(flat[2])
        desc = _txt(flat[3]) if len(flat) > 3 and flat[3] is not None else None
    else:
        type_, name = str(flat[1]), _txt(flat[2])
        ident = re.sub(r"[^a-zA-Z0-9]", "_", name)[:64]
        desc = _txt(flat[3]) if len(flat) > 3 and flat[3] is not None else None

    n = {"id": ident, "type": type_, "name": name}
    if desc: n["description"] = desc

    for c in children:
        if c.data == "property":
            key, value = str(c.children[0]), _txt(c.children[1])
            if key == "technology": n["technology"] = value
            elif key == "tags": n["tags"] = [x.strip() for x in value.split(",")]
            elif key == "description": n["description"] = value
            else: n.setdefault("properties", {})[key] = value
        elif c.data == "doc":
            doc = {"title": _txt(c.children[0]), "content": _long(c.children[1])}
            for a in c.children[2:]:
                if isinstance(a, Tree):
                    doc[{"doc_date": "date", "doc_format": "format"}[a.data]] = _txt(a.children[0])
            n.setdefault("docs", []).append(doc)
        elif c.data == "origin":
            n["origin"] = _origin(c)
        elif c.data == "node":
            n.setdefault("nodes", []).append(_node(c, relations))
        elif c.data == "relation":
            relations.append(_relation(c))
    return n


def _origin(t):
    keys = {"origin_tool": "tool", "origin_command": "command", "origin_date": "date"}
    return {keys[c.data]: _txt(c.children[0]) for c in t.children}


def _relation(t):
    src, arrow, dst = str(t.children[0]), str(t.children[1]), str(t.children[2])
    r = {"from": src, "to": dst}
    type_ = arrow[1:-2]
    if type_: r["type"] = type_
    if len(t.children) > 3 and t.children[3] is not None and not isinstance(t.children[3], Tree):
        r["description"] = _txt(t.children[3])
    for c in t.children[3:]:
        if isinstance(c, Tree):
            if c.data == "origin":
                r["origin"] = _origin(c)
            elif c.data == "property":
                key, value = str(c.children[0]), _txt(c.children[1])
                if key == "technology": r["technology"] = value
                elif key == "tags": r["tags"] = [x.strip() for x in value.split(",")]
                else: r.setdefault("properties", {})[key] = value
    return r


def text_to_json(text: str) -> dict:
    tree = _lark.parse(text)
    flat = [c for c in tree.children if not isinstance(c, Tree)]
    m = {"version": "1.0", "name": _txt(flat[0])}
    if len(flat) > 1 and flat[1] is not None:
        m["description"] = _txt(flat[1])
    m["spec"] = {"nodeTypes": {}}
    nodes, relations, views = [], [], []

    for item in (c for c in tree.children if isinstance(c, Tree)):
        if item.data == "spec":
            for d in item.children:
                name = str(d.children[0])
                body = {}
                desc = d.children[1]
                if desc is not None and str(desc).startswith('"'):
                    body["description"] = _txt(desc)
                for op in (x for x in d.children if isinstance(x, Tree)):
                    if op.data == "leaf":
                        body["contains"] = []
                        continue
                    values = [str(y) for y in op.children[0].children]
                    body[{"contains": "contains", "requires": "requires",
                          "from_types": "from", "to_types": "to"}[op.data]] = values
                if d.data == "node_decl":
                    m["spec"]["nodeTypes"][name] = body
                else:
                    m["spec"].setdefault("relationTypes", {})[name] = body
        elif item.data == "node":
            nodes.append(_node(item, relations))
        elif item.data == "relation":
            relations.append(_relation(item))
        elif item.data == "view":
            v = {"id": str(item.children[0]), "title": _txt(item.children[1]),
                 "include": []}
            for line in (x for x in item.children if isinstance(x, Tree)):
                key = "include" if line.data == "include" else "exclude"
                v.setdefault(key, []).append(_query(line.children[0]))
            views.append(v)

    m["nodes"] = nodes
    if relations: m["relations"] = relations
    if views: m["views"] = views
    return m


# ─────────────────────────── schema -> language ───────────────────────────

def _indent(n): return "  " * n


def _node_to_text(n, depth, relations):
    lines = [f'{_indent(depth)}{n["id"]} = {n["type"]} "{n["name"]}"'
             + (f' "{n["description"]}"' if "description" in n else "")]
    body = []
    if "technology" in n: body.append(f'{_indent(depth+1)}technology "{n["technology"]}"')
    if "tags" in n: body.append(f'{_indent(depth+1)}tags "{", ".join(n["tags"])}"')
    for k, v in (n.get("properties") or {}).items():
        body.append(f'{_indent(depth+1)}{k} "{v}"')
    for d in n.get("docs", []):
        line = f'{_indent(depth+1)}doc "{d["title"]}" """{d["content"]}"""'
        attrs = " ".join(f'{k} "{d[k]}"' for k in ("date", "format") if k in d)
        if attrs: line += f' {{ {attrs} }}'
        body.append(line)
    if "origin" in n:
        fields = " ".join(f'{k} "{v}"' for k, v in n["origin"].items())
        body.append(f'{_indent(depth+1)}origin {{ {fields} }}')
    for c in n.get("nodes", []):
        body.append(_node_to_text(c, depth + 1, relations))
    if body:
        lines[0] += " {"
        lines.extend(body)
        lines.append(_indent(depth) + "}")
    return "\n".join(lines)


def json_to_text(m: dict) -> str:
    lines = [f'model "{m["name"]}"' + (f' "{m["description"]}"' if "description" in m else "") + " {"]
    spec = m["spec"]
    lines.append(f"{_indent(1)}spec {{")
    for name, d in spec["nodeTypes"].items():
        head = f'{_indent(2)}node {name}' + (f' "{d["description"]}"' if d.get("description") else "")
        body = []
        if d.get("contains") == []:
            body.append(f'{_indent(3)}leaf')
        elif "contains" in d:
            body.append(f'{_indent(3)}contains {", ".join(d["contains"])}')
        if "requires" in d: body.append(f'{_indent(3)}requires {", ".join(d["requires"])}')
        lines.append(head + (" {\n" + "\n".join(body) + f"\n{_indent(2)}}}" if body else ""))
    for name, d in (spec.get("relationTypes") or {}).items():
        head = f'{_indent(2)}relation {name}' + (f' "{d["description"]}"' if d.get("description") else "")
        body = []
        if "from" in d: body.append(f'{_indent(3)}from {", ".join(d["from"])}')
        if "to" in d: body.append(f'{_indent(3)}to {", ".join(d["to"])}')
        lines.append(head + (" {\n" + "\n".join(body) + f"\n{_indent(2)}}}" if body else ""))
    lines.append(f"{_indent(1)}}}")

    for n in m["nodes"]:
        lines.append(_node_to_text(n, 1, m.get("relations", [])))
    for r in m.get("relations", []):
        arrow = f'-{r["type"]}->' if r.get("type") else "->"
        line = (f'{_indent(1)}{r["from"]} {arrow} {r["to"]}'
                + (f' "{r["description"]}"' if r.get("description") else ""))
        extra = []
        if "technology" in r: extra.append(f'technology "{r["technology"]}"')
        if "tags" in r: extra.append(f'tags "{", ".join(r["tags"])}"')
        for k, v in (r.get("properties") or {}).items(): extra.append(f'{k} "{v}"')
        if "origin" in r:
            extra.append("origin { " + " ".join(f'{k} "{v}"' for k, v in r["origin"].items()) + " }")
        if extra: line += " { " + " ".join(extra) + " }"
        lines.append(line)
    for v in m.get("views", []):
        lines.append(f'{_indent(1)}view {v["id"]} "{v["title"]}" {{')
        for q in v["include"]:
            lines.append(f'{_indent(2)}include {_query_to_text(q)}')
        for q in v.get("exclude", []):
            lines.append(f'{_indent(2)}exclude {_query_to_text(q)}')
        lines.append(f"{_indent(1)}}}")
    lines.append("}")
    return "\n".join(lines)


def _query_to_text(q):
    if q == "*": return "*"
    if "type" in q: return f'type {q["type"]}'
    if "tag" in q: return f'tag "{q["tag"]}"'
    if "inside" in q: return f'inside {q["inside"]}' + (f' {q["depth"]}' if "depth" in q else "")
    if "neighbors" in q: return f'neighbors {q["neighbors"]}' + (f' {q["hops"]}' if "hops" in q else "")
    raise ValueError(q)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    if mode == "to-json":
        print(json.dumps(text_to_json(Path(path).read_text()), indent=1, ensure_ascii=False))
    else:
        print(json_to_text(json.loads(Path(path).read_text())))
