"""Parse a Structurizr DSL workspace into a typed canonical model.

The test of whether a new format is worth anything is not that it looks nice,
but that it absorbs what already exists. This reads Structurizr's DSL and
honestly reports what it could NOT bring over, instead of hiding it.

Structurizr's nine fixed types become a declared spec: they stop being the
language and become configuration.  The parser builds typed ``Node``,
``Relation``, and ``View`` objects directly; ``loading`` calls ``to_dict()``
on the resulting ``Model`` and holds it to the normative schema — the same
gate every other input passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from .model import Inside, Model, Node, Relation, Spec, View

TYPES = {
    "person": "person",
    "softwareSystem": "softwareSystem",
    "container": "container",
    "component": "component",
    "deploymentNode": "deploymentNode",
    "infrastructureNode": "infrastructureNode",
    "containerInstance": "containerInstance",
    "softwareSystemInstance": "systemInstance",
    "group": "group",
}
SPEC: dict[str, Any] = {
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

# Parsed once at import; every call to parse() reuses the same typed Spec.
_SPEC: Spec = Spec.from_dict(SPEC)

_VIEW = re.compile(r"^(systemContext|container|component|dynamic|deployment)\s+(\S+)\s+(.*)")
_ELEMENT = re.compile(r"^(?:(\w+)\s*=\s*)?(\w+)\s+(\".*)")
_RELATION = re.compile(r"^(\S+)\s*->\s*(\S+)\s*(.*)")
_TAGS = re.compile(r"^tags\s+(.*)")
_LOST_PROPERTY = re.compile(r"^(description|technology|url|properties|perspectives)\b")

_TAGS_SLOT = 3  # name, description, technology, tags


def _ident(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:64] or "x"


def _strings(line: str) -> list[str]:
    return re.findall(r'"([^"]*)"', line)


def _slot(c: list[str], i: int) -> str:
    """The i-th quoted string of a declaration, or "" when the slot is absent."""
    return c[i] if len(c) > i else ""


@dataclass
class _Open:
    """An element opened with ``{``: its typed node and the children accumulated so far."""

    node: Node
    children: list[Node] = field(default_factory=list)


class _Parser:
    """Line-by-line state machine: which section we are in, which elements are
    open, how deep inside a view block.  One method per construct.

    The stack holds ``_Open`` entries for every element opened with ``{``.
    On ``}``, the element is finalised with its children and added to its parent.
    All nodes, relations, and views are typed from the moment of construction.
    """

    def __init__(self) -> None:
        self.lost: list[str] = []
        self.nodes: list[Node] = []
        self.relations: list[Relation] = []
        self.views: list[View] = []
        self.stack: list[_Open] = []  # open typed nodes
        self.section: str | None = None
        self.view_depth = 0
        self.root: dict[str, str] = {"name": "unnamed"}

    def feed(self, line: str) -> None:
        if not line or line.startswith(("//", "#")):
            return
        if re.match(r"^workspace\b", line):
            c = _strings(line)
            self.root = {"name": c[0] if c else "unnamed"}
            if _slot(c, 1):
                self.root["description"] = c[1]
        elif line in ("model {", "model{"):
            self.section = "model"
        elif line in ("views {", "views{"):
            self.section = "views"
        elif line == "}":
            self._close()
        elif self.section == "views":
            self._view_line(line)
        elif not (self._element(line) or self._relation(line) or self._property(line)):
            if line.startswith("!"):
                self.lost.append(f"directive: {line[:40]}")
            elif line != "{":
                self.lost.append(f"unrecognized: {line[:50]}")

    def _close(self) -> None:
        if self.view_depth:
            self.view_depth -= 1
        elif self.stack:
            open_item = self.stack.pop()
            # Finalise: attach children collected while the node was open.
            finalised = replace(open_item.node, nodes=tuple(open_item.children))
            if self.stack:
                self.stack[-1].children.append(finalised)
            else:
                self.nodes.append(finalised)
        elif self.section:
            self.section = None

    def _view_line(self, line: str) -> None:
        m = _VIEW.match(line)
        if m:
            c = _strings(m.group(3))
            title = c[0] if c else m.group(2)
            self.views.append(
                View(id=_ident(title), title=title, include=(Inside(_ident(m.group(2))),))
            )
            if line.endswith("{"):
                self.view_depth += 1
        elif line.startswith(("autolayout", "include", "exclude")):
            pass  # layout is the visualizer's call, not the model's
        elif line.startswith(("styles", "element", "relationship", "theme", "branding")):
            if line.endswith("{"):
                self.view_depth += 1
            self.lost.append(f"style or theme: {line[:44]}")
        else:
            self.lost.append(f"in views, unrecognized: {line[:44]}")

    def _element(self, line: str) -> bool:
        m = _ELEMENT.match(line)
        if not (m and m.group(2) in TYPES):
            return False
        var, type_ = m.group(1), TYPES[m.group(2)]
        c = _strings(m.group(3))
        node = Node(
            id=_ident(var or (c[0] if c else type_)),
            type=type_,
            name=c[0] if c else "?",
            description=_slot(c, 1),
            technology=_slot(c, 2),
            tags=tuple(x.strip() for x in c[_TAGS_SLOT].split(",")) if len(c) > _TAGS_SLOT else (),
        )
        if line.endswith("{"):
            self.stack.append(_Open(node))
        elif self.stack:
            self.stack[-1].children.append(node)
        else:
            self.nodes.append(node)
        return True

    def _relation(self, line: str) -> bool:
        m = _RELATION.match(line)
        if not m:
            return False
        c = _strings(m.group(3))
        self.relations.append(
            Relation(
                source=_ident(m.group(1)),
                target=_ident(m.group(2)),
                type="uses",
                description=_slot(c, 0),
                technology=_slot(c, 1),
            )
        )
        return True

    def _property(self, line: str) -> bool:
        if not self.stack:
            return False
        m = _TAGS.match(line)
        if m:
            extra = tuple(x.strip() for x in _strings(m.group(1)))
            open_item = self.stack[-1]
            open_item.node = replace(open_item.node, tags=open_item.node.tags + extra)
            return True
        if _LOST_PROPERTY.match(line):
            self.lost.append(f"element property: {line[:40]}")
            return True
        return False

    def model(self) -> Model:
        return Model(
            spec=_SPEC,
            nodes=tuple(self.nodes),
            relations=tuple(self.relations),
            views=tuple(self.views),
            name=self.root.get("name", "unnamed"),
            description=self.root.get("description", ""),
            version="1.0",
        )


@dataclass(frozen=True, slots=True)
class Parsed:
    """The result of parsing a Structurizr DSL workspace.

    ``model`` is the typed canonical model; ``lost`` is every construct the
    parser could not bring over, reported honestly rather than silently dropped.
    The model is not yet schema-checked here — ``loading.load()`` calls
    ``to_dict()`` on it and validates it against the normative schema, the same
    gate every other input passes.
    """

    model: Model
    lost: tuple[str, ...]


def parse(text: str) -> Parsed:
    """Parse ``text`` (Structurizr DSL) and return a typed ``Parsed`` result.

    ``loading`` calls ``to_dict()`` on the model inside ``Parsed`` and
    validates against the normative schema — the same gate every other input
    passes — before the model reaches any use case.
    """
    p = _Parser()
    for raw in text.splitlines():
        p.feed(raw.strip())
    return Parsed(model=p.model(), lost=tuple(p.lost))
