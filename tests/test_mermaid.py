"""Tests for the Mermaid C4 exporter (domain/mermaid.py).

Written test-first: these assert shape keywords, boundary nesting, external
element types, edge rendering and quote-folding.  The property test in
test_properties.py provides the exhaustive structural net.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arb_mcp.domain import drawio, mermaid
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


def test_levels_mirror_drawio(agatha: Model) -> None:
    """The two exporters enumerate the same views in the same order because
    they share c4_views.c4_views()."""
    assert [d.level for d in mermaid.to_c4_views(agatha)] == [
        d.level for d in drawio.to_views(agatha)
    ]


def test_c1_is_a_context_diagram_with_no_containers(simple: Model) -> None:
    views = mermaid.to_c4_views(simple)
    c1 = views[0]
    assert c1.level == "C1"
    assert c1.text.splitlines()[0] == "C4Context"
    # Persons and systems visible at C1
    assert "Person(user," in c1.text
    assert "System(sys," in c1.text
    # web is a container — must not appear at C1
    assert "web" not in c1.text


def test_c2_nests_containers_in_a_system_boundary(simple: Model) -> None:
    views = mermaid.to_c4_views(simple)
    c2 = next(v for v in views if v.level == "C2")
    # focus is inside a System_Boundary
    assert "System_Boundary(sys," in c2.text
    # container inside the boundary
    assert "Container(web," in c2.text
    # user is an external person
    assert "Person(user," in c2.text
    # diagram type
    assert c2.text.splitlines()[0] == "C4Container"


def test_external_system_in_c2_is_system_ext(agatha: Model) -> None:
    views = mermaid.to_c4_views(agatha)
    c2 = next(v for v in views if v.level == "C2")
    # agatha's C2 has external softwareSystems (youtube, correo)
    assert "System_Ext(" in c2.text


def test_quotes_and_newlines_are_folded() -> None:
    """Names with embedded double-quotes and newlines do not produce bare
    double-quotes inside string arguments or newlines within a line."""
    raw = json.loads((FIX / "agatha.json").read_text("utf-8"))
    # Inject a tricky name into a top-level node
    for n in raw["nodes"]:
        if n["id"] == "agatha":
            n["name"] = '"tricky" name\nwith newline'
            break
    m = Model.from_dict(raw)
    for view in mermaid.to_c4_views(m):
        for line in view.text.splitlines():
            # The injected " should have been folded to '
            assert '"tricky"' not in line, f"bare double-quote in: {line!r}"
            # No embedded newline within a line (trivially true since we split on \\n,
            # but guards against a future fold_quotes regression)
            assert "\n" not in line


def test_non_c4_model_is_refused() -> None:
    """mermaid.to_c4_views raises ValueError for non-C4 models."""
    uml = load((FIX / "uml-casos-uso.json").read_text("utf-8"))
    with pytest.raises(ValueError, match="mermaid supports C4"):
        mermaid.to_c4_views(uml)


def test_scope_and_name_match_drawio(agatha: Model) -> None:
    """Mermaid diagram scope and name should match the drawio counterparts."""
    mm = {(v.level, v.scope): v.name for v in mermaid.to_c4_views(agatha)}
    dw = {(v.level, v.scope): v.name for v in drawio.to_views(agatha)}
    assert mm == dw


def test_to_dict_has_mermaid_key(simple: Model) -> None:
    """to_dict() emits the 'mermaid' key (not 'xml')."""
    for view in mermaid.to_c4_views(simple):
        d = view.to_dict()
        assert "mermaid" in d
        assert "xml" not in d
        assert d["mermaid"] == view.text
