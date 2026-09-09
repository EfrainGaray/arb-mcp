"""The canonical model as typed values.

Everything else in the system speaks in these: the linter reads a ``Model``, the
exporters draw a ``Model``, the use cases carry a ``Model``. The JSON Schema
stays normative for the wire form; this module is its typed mirror, and
``Model.from_dict`` / ``Model.to_dict`` are the only two places that know the
two shapes. A dict that survives the schema always survives ``from_dict``, and
``to_dict`` gives back the same facts — so the vendored engine, which still
reads dicts, is fed through ``to_dict()`` at its boundary and nothing above it
touches a string key again.

Values are frozen: a use case cannot mutate a node the caller still holds, and
two models built from the same facts compare equal.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

Json = dict[str, Any]

_EMPTY: Mapping[str, Any] = MappingProxyType({})


def _strs(value: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in (value or ()))


def _mapping(value: Any) -> Mapping[str, Any]:
    return MappingProxyType(dict(value)) if value else _EMPTY


def _put(out: Json, key: str, value: Any) -> None:
    """Emit only what carries information: an absent optional and an empty one
    are the same fact, and emitting neither keeps the wire form minimal."""
    if value is None or value in ("", (), {}, _EMPTY):
        return
    if isinstance(value, Mapping):
        out[key] = dict(value)
    elif isinstance(value, tuple):
        out[key] = list(value)
    else:
        out[key] = value


# ── spec: the vocabulary a model declares ─────────────────────────────────────
@dataclass(frozen=True, slots=True)
class NodeType:
    description: str = ""
    contains: tuple[str, ...] | None = None  # None = anything; () = a leaf
    requires: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> NodeType:
        contains = d.get("contains")
        return cls(
            description=str(d.get("description", "")),
            contains=None if contains is None else _strs(contains),
            requires=_strs(d.get("requires")),
        )

    def to_dict(self) -> Json:
        out: Json = {}
        _put(out, "description", self.description)
        if self.contains is not None:
            out["contains"] = list(self.contains)
        _put(out, "requires", self.requires)
        return out


@dataclass(frozen=True, slots=True)
class RelationType:
    description: str = ""
    sources: tuple[str, ...] | None = None  # None = any node type
    targets: tuple[str, ...] | None = None
    directed: bool = True

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RelationType:
        src, dst = d.get("from"), d.get("to")
        return cls(
            description=str(d.get("description", "")),
            sources=None if src is None else _strs(src),
            targets=None if dst is None else _strs(dst),
            directed=bool(d.get("directed", True)),
        )

    def to_dict(self) -> Json:
        out: Json = {}
        _put(out, "description", self.description)
        if self.sources is not None:
            out["from"] = list(self.sources)
        if self.targets is not None:
            out["to"] = list(self.targets)
        if not self.directed:
            out["directed"] = False
        return out


@dataclass(frozen=True, slots=True)
class Spec:
    node_types: Mapping[str, NodeType]
    relation_types: Mapping[str, RelationType] = _EMPTY
    extends: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Spec:
        return cls(
            node_types=MappingProxyType(
                {k: NodeType.from_dict(v or {}) for k, v in (d.get("nodeTypes") or {}).items()}
            ),
            relation_types=MappingProxyType(
                {
                    k: RelationType.from_dict(v or {})
                    for k, v in (d.get("relationTypes") or {}).items()
                }
            ),
            extends=str(d.get("extends", "")),
        )

    def to_dict(self) -> Json:
        out: Json = {"nodeTypes": {k: v.to_dict() for k, v in self.node_types.items()}}
        if self.relation_types:
            out["relationTypes"] = {k: v.to_dict() for k, v in self.relation_types.items()}
        _put(out, "extends", self.extends)
        return out

    @property
    def default_relation_type(self) -> str | None:
        """The first declared relation type (``uses`` for C4), or None."""
        return next(iter(self.relation_types), None)

    @property
    def is_c4(self) -> bool:
        return "softwareSystem" in self.node_types and "container" in self.node_types


# ── elements ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Doc:
    title: str
    content: str
    format: str = "markdown"
    date: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Doc:
        return cls(
            title=str(d["title"]),
            content=str(d["content"]),
            format=str(d.get("format", "markdown")),
            date=str(d.get("date", "")),
        )

    def to_dict(self) -> Json:
        out: Json = {"title": self.title, "content": self.content}
        if self.format != "markdown":
            out["format"] = self.format
        _put(out, "date", self.date)
        return out


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    type: str
    name: str
    description: str = ""
    technology: str = ""
    tags: tuple[str, ...] = ()
    properties: Mapping[str, str] = _EMPTY
    nodes: tuple[Node, ...] = ()
    docs: tuple[Doc, ...] = ()
    origin: Mapping[str, str] = _EMPTY

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Node:
        return cls(
            id=str(d["id"]),
            type=str(d["type"]),
            name=str(d.get("name", d["id"])),
            description=str(d.get("description", "")),
            technology=str(d.get("technology", "")),
            tags=_strs(d.get("tags")),
            properties=_mapping(d.get("properties")),
            nodes=tuple(Node.from_dict(c) for c in d.get("nodes") or ()),
            docs=tuple(Doc.from_dict(x) for x in d.get("docs") or ()),
            origin=_mapping(d.get("origin")),
        )

    def to_dict(self) -> Json:
        out: Json = {"id": self.id, "type": self.type, "name": self.name}
        _put(out, "description", self.description)
        _put(out, "technology", self.technology)
        _put(out, "tags", self.tags)
        _put(out, "properties", self.properties)
        if self.nodes:
            out["nodes"] = [c.to_dict() for c in self.nodes]
        if self.docs:
            out["docs"] = [x.to_dict() for x in self.docs]
        _put(out, "origin", self.origin)
        return out

    def walk(self) -> Iterator[Node]:
        """This node, then every descendant, depth-first in declaration order."""
        yield self
        for c in self.nodes:
            yield from c.walk()

    def children_of_type(self, *types: str) -> tuple[Node, ...]:
        return tuple(c for c in self.nodes if c.type in types)


@dataclass(frozen=True, slots=True)
class Relation:
    source: str
    target: str
    type: str = ""
    description: str = ""
    technology: str = ""
    tags: tuple[str, ...] = ()
    properties: Mapping[str, str] = _EMPTY
    id: str = ""
    origin: Mapping[str, str] = _EMPTY

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Relation:
        return cls(
            source=str(d["from"]),
            target=str(d["to"]),
            type=str(d.get("type", "")),
            description=str(d.get("description", "")),
            technology=str(d.get("technology", "")),
            tags=_strs(d.get("tags")),
            properties=_mapping(d.get("properties")),
            id=str(d.get("id", "")),
            origin=_mapping(d.get("origin")),
        )

    def to_dict(self) -> Json:
        out: Json = {"from": self.source, "to": self.target}
        _put(out, "id", self.id)
        _put(out, "type", self.type)
        _put(out, "description", self.description)
        _put(out, "technology", self.technology)
        _put(out, "tags", self.tags)
        _put(out, "properties", self.properties)
        _put(out, "origin", self.origin)
        return out

    @property
    def implied(self) -> bool:
        """Derived by the implied-relations transformation, not written by a person."""
        return "implied" in self.tags


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a node sits, as a CELL and not as pixels: ``rank`` is the reading
    depth and ``order`` the position within it, both relative to the parent."""

    node: str
    rank: int
    order: int
    span: int = 1

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Placement:
        return cls(
            node=str(d["node"]),
            rank=int(d["rank"]),
            order=int(d["order"]),
            span=int(d.get("span", 1)),
        )

    def to_dict(self) -> Json:
        out: Json = {"node": self.node, "rank": self.rank, "order": self.order}
        if self.span != 1:
            out["span"] = self.span
        return out


@dataclass(frozen=True, slots=True)
class Layout:
    """A partial, ordinal overlay on a view. It carries no pixel: the model
    states order, a render profile states size, and the exporter does the
    arithmetic. A node the view returns and this does not mention is placed by
    the exporter and marked derived."""

    direction: str = "down"  # down | up | right | left
    placements: tuple[Placement, ...] = ()
    origin: str = ""  # manual | imported | derived
    tool: str = ""
    model_digest: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Layout:
        return cls(
            direction=str(d.get("direction", "down")),
            placements=tuple(Placement.from_dict(p) for p in d.get("placements") or ()),
            origin=str(d.get("origin", "")),
            tool=str(d.get("tool", "")),
            model_digest=str(d.get("modelDigest", "")),
        )

    def to_dict(self) -> Json:
        out: Json = {
            "direction": self.direction,
            "placements": [p.to_dict() for p in self.placements],
        }
        _put(out, "origin", self.origin)
        _put(out, "tool", self.tool)
        _put(out, "modelDigest", self.model_digest)
        return out


@dataclass(frozen=True, slots=True)
class View:
    id: str
    title: str
    include: tuple[Any, ...]  # queries: "*" or {type|tag|inside|neighbors: ...}
    exclude: tuple[Any, ...] = ()
    description: str = ""
    layout: Layout | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> View:
        layout = d.get("layout")
        return cls(
            id=str(d["id"]),
            title=str(d["title"]),
            include=tuple(d.get("include") or ()),
            exclude=tuple(d.get("exclude") or ()),
            description=str(d.get("description", "")),
            layout=Layout.from_dict(layout) if layout else None,
        )

    def to_dict(self) -> Json:
        out: Json = {"id": self.id, "title": self.title, "include": list(self.include)}
        _put(out, "exclude", self.exclude)
        _put(out, "description", self.description)
        if self.layout is not None:
            out["layout"] = self.layout.to_dict()
        return out


# ── the model ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Model:
    spec: Spec
    nodes: tuple[Node, ...]
    relations: tuple[Relation, ...] = ()
    views: tuple[View, ...] = ()
    name: str = ""
    description: str = ""
    scope: str = ""  # landscape | system | deployment | undefined | "" (absent)
    version: str = "1.0"
    _by_id: Mapping[str, Node] = field(init=False, repr=False, compare=False)
    _parent: Mapping[str, str | None] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_id: dict[str, Node] = {}
        parent: dict[str, str | None] = {}

        def index(nodes: tuple[Node, ...], up: str | None) -> None:
            for n in nodes:
                by_id[n.id] = n
                parent[n.id] = up
                index(n.nodes, n.id)

        index(self.nodes, None)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_parent", MappingProxyType(parent))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Model:
        """Build from a schema-valid dict. Validate first; this trusts its input."""
        return cls(
            spec=Spec.from_dict(d.get("spec") or {}),
            nodes=tuple(Node.from_dict(n) for n in d.get("nodes") or ()),
            relations=tuple(Relation.from_dict(r) for r in d.get("relations") or ()),
            views=tuple(View.from_dict(v) for v in d.get("views") or ()),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            scope=str(d.get("scope", "")),
            version=str(d.get("version", "1.0")),
        )

    def to_dict(self) -> Json:
        out: Json = {"version": self.version}
        _put(out, "name", self.name)
        _put(out, "description", self.description)
        _put(out, "scope", self.scope)
        out["spec"] = self.spec.to_dict()
        out["nodes"] = [n.to_dict() for n in self.nodes]
        if self.relations:
            out["relations"] = [r.to_dict() for r in self.relations]
        if self.views:
            out["views"] = [v.to_dict() for v in self.views]
        return out

    # ── navigation ──
    def walk(self) -> Iterator[Node]:
        """Every node at every depth, depth-first in declaration order."""
        for n in self.nodes:
            yield from n.walk()

    def get(self, node_id: str) -> Node | None:
        return self._by_id.get(node_id)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._by_id

    def parent_of(self, node_id: str) -> str | None:
        return self._parent.get(node_id)

    def top_of(self, node_id: str) -> str:
        """The top-level ancestor id of ``node_id`` (itself when top-level)."""
        cur = node_id
        while (up := self._parent.get(cur)) is not None:
            cur = up
        return cur

    def lift_to(self, node_id: str, wanted: set[str]) -> str | None:
        """The nearest ancestor of ``node_id`` (itself included) that is in ``wanted``."""
        cur: str | None = node_id
        while cur is not None:
            if cur in wanted:
                return cur
            cur = self._parent.get(cur)
        return None

    def written_relations(self) -> tuple[Relation, ...]:
        """Relations a person declared: everything not tagged ``implied``."""
        return tuple(r for r in self.relations if not r.implied)

    @property
    def is_c4(self) -> bool:
        return self.spec.is_c4
