"""Cells to pixels: deterministic, authored placements honoured, the rest derived,
and the render profile kept out of the model."""

from __future__ import annotations

import json
from itertools import pairwise
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
    """Same arithmetic on a turned page: what ran down the page now runs across
    it, in the same order.

    The boxes do NOT turn with it -- a box stays as wide and as tall as its
    profile says -- so the coordinates are not a plain transposition of the
    down-flowing ones. They used to be, and that was the defect: consecutive
    ranks were then stepped by the box's height while its width had to clear.
    """
    down = resolve(_boxes(), Layout("down"), GRID)
    right = resolve(_boxes(), Layout("right"), GRID)

    d_sys, d_ext = down.get("sys"), down.get("ext")
    r_sys, r_ext = right.get("sys"), right.get("ext")
    assert d_sys and d_ext and r_sys and r_ext

    # down: one below the other; right: one beside it. Centred across the other
    # axis either way, so the coordinate that does not advance is the midpoint.
    assert d_ext.y > d_sys.y
    assert d_ext.x + d_ext.w / 2 == d_sys.x + d_sys.w / 2
    assert r_ext.x > r_sys.x
    assert r_ext.y + r_ext.h / 2 == r_sys.y + r_sys.h / 2
    assert (r_ext.w, r_ext.h) == (d_ext.w, d_ext.h)  # the box kept its own size
    assert r_ext.x >= r_sys.x + r_sys.w  # and they do not overlap


def test_a_right_flowing_layout_separates_ranks_by_the_width_of_a_box() -> None:
    """Reading to the right means consecutive ranks sit side by side, so the gap
    between them has to clear the box's WIDTH.

    The transposition swapped each box's x and y but left its width and height
    alone, so the step between ranks came from the height instead: with wide,
    short C4 boxes (240x120) every rank overlapped the next by half a box.
    """
    ancho, alto = 240, 120
    cajas = tuple(Box(n, None, (ancho, alto)) for n in ("a", "b", "c"))
    layout = Layout(
        direction="right",
        placements=tuple(Placement(node=n, rank=i, order=0) for i, n in enumerate("abc")),
    )
    resuelto = resolve(cajas, layout, GRID)
    puestos = [resuelto.get(n) for n in ("a", "b", "c")]
    assert all(p is not None for p in puestos)

    for antes, despues in pairwise(puestos):
        assert antes is not None and despues is not None
        assert despues.x >= antes.x + antes.w, f"{despues.id} monta sobre {antes.id}"
        assert despues.y == antes.y, "one rank per column: same row"
        assert (despues.w, despues.h) == (ancho, alto), "the box keeps its own size"


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


def test_reading_sideways_leaves_room_for_an_edge_label_between_ranks() -> None:
    """An edge label is wide and short. Between rows its height has to clear;
    between columns its width does, and that is several times larger.

    One gap served both, so a right-flowing diagram put every label on top of
    the box it pointed at.
    """
    cajas = (Box("a", None, (240, 120)), Box("b", None, (240, 120)))
    celdas = (Placement("a", 0, 0), Placement("b", 1, 0))
    grid = Grid(rank_gap=80, order_gap=60, label_room=70, edge_label_room=160)

    abajo = resolve(cajas, Layout("down", placements=celdas), grid)
    a_ab, b_ab = abajo.get("a"), abajo.get("b")
    assert a_ab and b_ab
    assert b_ab.y - (a_ab.y + a_ab.h) == grid.rank_gap

    lado = resolve(cajas, Layout("right", placements=celdas), grid)
    a_la, b_la = lado.get("a"), lado.get("b")
    assert a_la and b_la
    assert b_la.x - (a_la.x + a_la.w) == grid.edge_label_room


def test_a_rank_is_centred_against_the_widest_one() -> None:
    """A lone node in its rank belongs in the middle of the diagram, not pinned
    to the left edge.

    Each rank started at the same origin, so a single node under a row of three
    sat under the FIRST of them and every edge to the other two crossed the
    picture on its way down.
    """
    cajas = (
        Box("a", None, (240, 120)),
        Box("b", None, (240, 120)),
        Box("c", None, (240, 120)),
        Box("solo", None, (240, 120)),
    )
    layout = Layout(
        direction="down",
        placements=(
            Placement("a", 0, 0),
            Placement("b", 0, 1),
            Placement("c", 0, 2),
            Placement("solo", 1, 0),
        ),
    )
    r = resolve(cajas, layout, GRID)
    a, c, solo = r.get("a"), r.get("c"), r.get("solo")
    assert a and c and solo

    fila = (a.x, c.x + c.w)
    centro_fila = (fila[0] + fila[1]) / 2
    assert solo.x + solo.w / 2 == centro_fila


def test_left_and_up_reverse_the_reading_axis_of_right_and_down() -> None:
    """Reading backwards mirrors along the axis the ranks advance on.

    The mirror always flipped y, which is the reading axis only when the page
    runs down. Laid out sideways the ranks advance on x, so flipping y left the
    order untouched: a left-flowing diagram came out identical to a right-flowing
    one, and the schema accepts all four directions.
    """
    cajas = tuple(Box(n, None, (240, 120)) for n in ("a", "b", "c"))
    celdas = tuple(Placement(n, i, 0) for i, n in enumerate(("a", "b", "c")))

    def ejes(direccion: str) -> list[int]:
        r = resolve(cajas, Layout(direccion, placements=celdas), GRID)
        puestos = [r.get(n) for n in ("a", "b", "c")]
        assert all(p is not None for p in puestos)
        horizontal = direccion in ("right", "left")
        return [p.x if horizontal else p.y for p in puestos if p is not None]

    derecha, izquierda = ejes("right"), ejes("left")
    abajo, arriba = ejes("down"), ejes("up")

    assert derecha == sorted(derecha), "right: a, b, c across the page"
    assert izquierda == sorted(izquierda, reverse=True), "left: c, b, a across the page"
    assert abajo == sorted(abajo), "down: a, b, c down the page"
    assert arriba == sorted(arriba, reverse=True), "up: c, b, a down the page"

    # Mirroring moves the boxes, it does not squash the diagram.
    assert sorted(izquierda) == derecha
    assert sorted(arriba) == abajo


def test_a_mirrored_child_keeps_the_padding_its_parent_reserves() -> None:
    """Flipping happens inside the parent's own box, so the gap a container keeps
    around its children survives the mirror instead of being eaten at one edge.

    The mirror measured against how far the children reached rather than against
    the parent, so the last of them landed hard on the boundary at 0.
    """
    cajas = (Box("sys", None, (240, 210)), Box("a", "sys", (240, 120)))
    celdas = (Placement("a", 0, 0),)

    abajo = resolve(cajas, Layout("down", placements=celdas), GRID)
    arriba = resolve(cajas, Layout("up", placements=celdas), GRID)
    a_ab, a_ar = abajo.get("a"), arriba.get("a")
    assert a_ab and a_ar
    assert a_ab.y > 0, "a child is inset from the top of its parent"
    assert a_ar.y > 0, "and stays inset when the parent is read bottom-up"


def test_the_landscape_takes_its_layout_from_any_top_level_view() -> None:
    """A context view can select its members however it likes -- `*`, or by type
    -- and its geometry has to be honoured either way.

    Only `*` was recognised, so a view that listed `{"type": "person"}` and
    `{"type": "softwareSystem"}` had its layout silently dropped and the C1 came
    out as one column. Silently is the part that matters: the model was right and
    the picture was wrong.
    """
    crudo = {
        "version": "1.0",
        "scope": "system",
        "spec": {
            "nodeTypes": {
                "person": {"contains": []},
                "softwareSystem": {"contains": ["container"]},
                "container": {"contains": []},
            },
            "relationTypes": {"uses": {}},
        },
        "nodes": [
            {"id": "a", "type": "person", "name": "A"},
            {"id": "b", "type": "person", "name": "B"},
            {
                "id": "s",
                "type": "softwareSystem",
                "name": "S",
                "nodes": [{"id": "c", "type": "container", "name": "C"}],
            },
        ],
        "relations": [{"from": "a", "to": "c", "type": "uses"}],
        "views": [
            {
                "id": "ctx",
                "title": "Contexto",
                "include": [{"type": "person"}, {"type": "softwareSystem"}],
                "layout": {
                    "direction": "down",
                    "placements": [
                        {"node": "a", "rank": 0, "order": 0},
                        {"node": "b", "rank": 0, "order": 1},
                        {"node": "s", "rank": 1, "order": 0},
                    ],
                },
            }
        ],
    }
    c1 = next(v for v in drawio_views(load(json.dumps(crudo))) if v["level"] == "C1")
    root = ET.fromstring(c1["xml"])
    geo = {}
    for celda in root.iter("mxCell"):
        g = celda.find("mxGeometry")
        if celda.get("id") and g is not None:
            geo[celda.get("id")] = g
    for obj in root.iter("object"):
        g = obj.find("mxCell/mxGeometry")
        if obj.get("id") and g is not None:
            geo[obj.get("id")] = g

    a, b = geo.get("a"), geo.get("b")
    assert a is not None and b is not None
    assert a.get("y") == b.get("y"), "the two actors were authored side by side"
    assert a.get("x") != b.get("x")
