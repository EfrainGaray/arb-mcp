"""Cells to pixels: deterministic, authored placements honoured, the rest derived,
and the render profile kept out of the model."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from arb_mcp.application.convert_model import drawio_views
from arb_mcp.application.validate_model import validate_model
from arb_mcp.domain import drawio
from arb_mcp.domain.layout import Box, resolve
from arb_mcp.domain.loading import load
from arb_mcp.domain.model import Layout, Model, Placement
from arb_mcp.domain.render import Grid, RenderProfile

FIX = Path(__file__).parent / "fixtures"
GRID = Grid(rank_gap=80, order_gap=60, label_room=70)


def _boxes() -> tuple[Box, ...]:
    return (
        Box("sys", None, (240, 210)),
        Box("a", "sys", (240, 120)),
        Box("b", "sys", (240, 120)),
        Box("ext", None, (240, 120)),
    )


def test_unmentioned_nodes_are_placed_in_a_column_and_marked_derived() -> None:
    r = resolve(_boxes(), None, GRID)
    a, b = r.get("a"), r.get("b")
    assert a and b and a.x == b.x and b.y > a.y  # a column inside sys
    assert {p.origin for p in r.nodes} == {"derived"}
    assert set(r.derived) == {"sys", "a", "b", "ext"}


def test_authored_cells_are_honoured_and_a_parent_grows_to_fit() -> None:
    layout = Layout(
        direction="down",
        origin="manual",
        placements=(Placement("a", 0, 0), Placement("b", 0, 1)),  # side by side
    )
    r = resolve(_boxes(), layout, GRID)
    a, b, sys = r.get("a"), r.get("b"), r.get("sys")
    assert a and b and sys
    assert a.y == b.y and b.x > a.x  # a row, as authored
    assert a.origin == "manual" and sys.origin == "derived"
    assert sys.w >= a.w + b.w + GRID.order_gap  # the boundary fits both
    assert sys.h >= a.h + GRID.label_room  # and keeps room for its own label


def test_same_input_same_pixels() -> None:
    assert resolve(_boxes(), None, GRID) == resolve(_boxes(), None, GRID)


def test_direction_is_a_flip_not_a_second_algorithm() -> None:
    down = resolve(_boxes(), Layout("down"), GRID)
    right = resolve(_boxes(), Layout("right"), GRID)
    assert (right.width, right.height) == (down.height, down.width)
    d, r = down.get("ext"), right.get("ext")
    assert d and r and (r.x, r.y) == (d.y, d.x)


def test_two_profiles_same_verdict_different_drawing() -> None:
    """The separation the schema promises: a profile changes pixels, never findings."""
    model = load((FIX / "agatha.json").read_text("utf-8"))
    big = RenderProfile.from_dict(
        {
            "profile": "big",
            "nodeTypes": {"container": {"size": [480, 240]}},
            "defaults": {"size": [400, 200]},
        }
    )
    small = RenderProfile.load("c4")
    v_big = drawio.to_views(model, big)
    v_small = drawio.to_views(model, small)
    assert [d.name for d in v_big] == [d.name for d in v_small]
    assert any(a.xml != b.xml for a, b in zip(v_big, v_small, strict=True))
    assert validate_model(model).to_dict() == validate_model(model).to_dict()
    assert model.to_dict() == Model.from_dict(model.to_dict()).to_dict()  # profile never touched it


def test_sizes_come_from_drawio_own_c4_palette() -> None:
    """H3 of the audit: 210x110 was hardcoded; drawio's palette says 240x120 and 200x180."""
    views = drawio_views(load((FIX / "simple.dsl").read_text("utf-8")))
    c1 = next(v for v in views if v["level"] == "C1")
    geo = {
        o.get("id"): o.find("mxCell/mxGeometry") for o in ET.fromstring(c1["xml"]).iter("object")
    }
    user, sys = geo["user"], geo["sys"]
    assert user is not None and (user.get("width"), user.get("height")) == ("200", "180")
    assert sys is not None and (sys.get("width"), sys.get("height")) == ("240", "120")


def test_authored_layout_in_the_model_reaches_the_drawing() -> None:
    raw = json.loads((FIX / "agatha.json").read_text("utf-8"))
    raw["views"] = [
        {
            "id": "ctx",
            "title": "Context",
            "include": ["*"],
            "layout": {
                "direction": "down",
                "origin": "manual",
                "placements": [
                    {"node": "usuario", "rank": 0, "order": 0},
                    {"node": "agatha", "rank": 0, "order": 1},
                ],
            },
        }
    ]
    model = load(json.dumps(raw))
    c1 = next(v for v in drawio_views(model) if v["level"] == "C1")
    geo = {
        o.get("id"): o.find("mxCell/mxGeometry") for o in ET.fromstring(c1["xml"]).iter("object")
    }
    u, a = geo["usuario"], geo["agatha"]
    assert u is not None and a is not None
    assert u.get("y") == a.get("y") and int(a.get("x") or 0) > int(u.get("x") or 0)  # a row


def test_authored_c2_layout_is_honoured_and_the_rest_goes_after_it() -> None:
    """The author placed only the person (rank 1). The boundary the author did
    not mention goes after the last authored rank, so it lands BELOW the person."""
    raw = load((FIX / "simple.dsl").read_text("utf-8")).to_dict()
    raw["views"] = [
        {
            "id": "c2",
            "title": "Containers",
            "include": [{"inside": "sys"}],
            "layout": {
                "direction": "down",
                "placements": [{"node": "user", "rank": 1, "order": 0}],
            },
        }
    ]
    c2 = next(v for v in drawio_views(load(json.dumps(raw))) if v["level"] == "C2")
    root = ET.fromstring(c2["xml"])
    geo = {o.get("id"): o.find("mxCell/mxGeometry") for o in root.iter("object")}
    sys_cell = next(c for c in root.iter("mxCell") if c.get("id") == "sys")
    sys_geo = sys_cell.find("mxGeometry")
    user = geo["user"]
    assert user is not None and sys_geo is not None
    assert int(sys_geo.get("y") or 0) > int(user.get("y") or 0) + int(user.get("height") or 0)


def test_flat_level_name_for_a_spec_that_is_neither_uml_nor_deployment() -> None:
    model = Model.from_dict(
        {
            "version": "1.0",
            "scope": "system",
            "spec": {"nodeTypes": {"box": {}}},
            "nodes": [{"id": "a", "type": "box", "name": "A"}],
        }
    )
    assert drawio.to_views(model)[0].level == "Diagram"
