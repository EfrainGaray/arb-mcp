"""Views are queries: each shape selects what the schema says, exclude wins,
and the linter reports a query that names a ghost or a view that shows nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arb_mcp.domain.linter import lint
from arb_mcp.domain.loading import load
from arb_mcp.domain.model import All, ByTag, ByType, Inside, Neighbors, View
from arb_mcp.domain.views import members

FIX = Path(__file__).parent / "fixtures"
AGATHA: dict[str, Any] = json.loads((FIX / "agatha.json").read_text("utf-8"))


def _ids(*queries: Any, exclude: tuple[Any, ...] = ()) -> list[str]:
    model = load(json.dumps(AGATHA))
    view = View(id="v", title="v", include=tuple(queries), exclude=exclude)
    return [n.id for n in members(model, view)]


def test_star_is_every_element_in_model_order() -> None:
    model = load(json.dumps(AGATHA))
    assert _ids(All()) == [n.id for n in model.walk()]


def test_type_and_tag_select_by_declaration() -> None:
    assert _ids(ByType("person")) == ["usuario"]
    assert _ids(ByTag("no-such-tag")) == []


def test_inside_walks_down_to_the_given_depth_without_the_root() -> None:
    one = _ids(Inside("agatha"))
    deep = _ids(Inside("agatha", depth=2))
    assert "agatha" not in one and one and set(one) < set(deep)
    assert all(d in deep for d in ("api", "escaner", "cli", "almacen", "core"))


def test_neighbors_walk_relations_both_ways_by_hops() -> None:
    one = set(_ids(Neighbors("usuario")))
    two = set(_ids(Neighbors("usuario", hops=2)))
    assert "usuario" in one and "api" in one  # usuario -> api
    assert one < two


def test_exclude_is_applied_after_include() -> None:
    assert "usuario" not in _ids(All(), exclude=(ByType("person"),))


def test_query_naming_a_ghost_is_blocking_and_an_empty_view_warns() -> None:
    raw = dict(AGATHA)
    raw["views"] = [
        {"id": "ghosted", "title": "g", "include": [{"inside": "nope"}]},
        {"id": "nothing", "title": "n", "include": [{"tag": "unused"}]},
    ]
    findings = lint(load(json.dumps(raw)))
    rules = {(f.rule, f.severity.value) for f in findings}
    assert ("view.query.node", "ERROR") in rules
    assert ("view.empty", "WARNING") in rules


def test_queries_round_trip_the_wire_form() -> None:
    raw = dict(AGATHA)
    raw["views"] = [
        {
            "id": "v",
            "title": "v",
            "include": ["*", {"type": "container"}, {"inside": "agatha", "depth": 2}],
            "exclude": [{"tag": "x"}, {"neighbors": "usuario", "hops": 3}],
        }
    ]
    model = load(json.dumps(raw))
    assert model.to_dict()["views"] == raw["views"]
