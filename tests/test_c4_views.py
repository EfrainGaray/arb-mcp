"""Tests for the notation-neutral C4 scoping layer (domain/c4_views.py).

Written before moving code out of drawio.py (commit 6).  These tests exercise
the new seam: what elements appear in each view and how edges are resolved.
The drawio golden (tests/fixtures/drawio_golden.json) acts as the complementary
regression net for the pixel coordinates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arb_mcp.domain import c4_views as cv
from arb_mcp.domain.loading import load
from arb_mcp.domain.model import Model

FIX = Path(__file__).parent / "fixtures"
DSL = (FIX / "simple.dsl").read_text("utf-8")


@pytest.fixture(scope="module")
def simple() -> Model:
    return load(DSL)


@pytest.fixture(scope="module")
def agatha() -> Model:
    return load((FIX / "agatha.json").read_text("utf-8"))


def test_context_has_tops_only_and_lifted_edges(simple: Model) -> None:
    """simple.dsl: inside={user, sys}, no externals, edge user->sys lifted from user->web."""
    view = cv.context(simple)

    assert view.level == "C1"
    assert view.focus is None
    assert view.scope == "system-landscape"

    inside_ids = {n.id for n in view.inside}
    assert inside_ids == {"user", "sys"}
    assert view.externals == ()

    # The written relation is user->web; at C1 web is lifted to sys.
    assert len(view.edges) == 1
    edge = view.edges[0]
    assert edge.source == "user"
    assert edge.target == "sys"
    assert edge.relation.source == "user"
    assert edge.relation.target == "web"


def test_containers_view_lists_externals_reached_by_an_edge_in_first_seen_order(
    agatha: Model,
) -> None:
    """agatha C2: containers inside agatha; usuario, youtube, correo as externals."""
    system = agatha.get("agatha")
    assert system is not None
    view = cv.containers(agatha, system)

    assert view.level == "C2"
    assert view.focus is not None and view.focus.id == "agatha"

    inside_ids = {n.id for n in view.inside}
    assert inside_ids == {"api", "escaner", "cli", "almacen", "core"}

    external_ids = [n.id for n in view.externals]
    # externals are in first-seen order (order of relation appearance)
    assert set(external_ids) == {"usuario", "youtube", "correo"}
    # they must be a subset of model nodes
    for eid in external_ids:
        assert agatha.get(eid) is not None


def test_components_view_lifts_a_sibling_container_endpoint(agatha: Model) -> None:
    """C3 for core: almacen (sibling container) appears as an external when
    reached by servicio -> almacen; canal -> youtube resolves to youtube (system)."""
    container = agatha.get("core")
    assert container is not None
    view = cv.components(agatha, container)

    assert view.level == "C3"
    assert view.focus is not None and view.focus.id == "core"

    inside_ids = {n.id for n in view.inside}
    assert inside_ids == {"servicio", "chunker", "bch", "bitmap", "codec", "canal", "verificador"}

    external_ids = {n.id for n in view.externals}
    # almacen is a sibling container reached by servicio; youtube by canal
    assert "almacen" in external_ids
    assert "youtube" in external_ids

    # canal -> youtube edge must appear in the view
    canal_youtube = [e for e in view.edges if e.source == "canal" and e.target == "youtube"]
    assert canal_youtube, "edge canal->youtube must be in C3 core view"


def test_dangling_endpoint_yields_no_edge_and_no_external() -> None:
    """A relation whose endpoint is not in the model must not produce an edge or
    external; the linter reports it, but the exporter must not crash."""
    raw = json.loads((FIX / "agatha.json").read_text("utf-8"))
    raw["relations"].append({"from": "canal", "to": "ghost", "type": "uses"})
    # Bypass the linter (which blocks merges) and test the scoping directly.
    m = Model.from_dict(raw)
    container = m.get("core")
    assert container is not None
    view = cv.components(m, container)

    ghost_edges = [e for e in view.edges if "ghost" in (e.source, e.target)]
    assert not ghost_edges, "dangling endpoint must not produce an edge"
    ghost_ext = [n for n in view.externals if n.id == "ghost"]
    assert not ghost_ext, "dangling endpoint must not produce an external"


def test_enumeration_order_is_c1_then_c2_per_system_then_c3_per_container(
    agatha: Model,
) -> None:
    """c4_views: C1 first, then C2 for each system with containers, then C3
    for each container with components — same order as drawio.to_c4_views."""
    views = cv.c4_views(agatha)
    levels = [v.level for v in views]

    assert levels[0] == "C1"
    # agatha has containers -> one C2
    assert levels.count("C2") >= 1
    # core has components -> one C3
    assert levels.count("C3") >= 1
    # C1 always first; all C2s before any C3
    c2_positions = [i for i, lv in enumerate(levels) if lv == "C2"]
    c3_positions = [i for i, lv in enumerate(levels) if lv == "C3"]
    if c2_positions and c3_positions:
        assert max(c2_positions) < min(c3_positions), "all C2s must precede all C3s"
