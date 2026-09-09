"""Structurizr export: the emitted DSL round-trips back through the loader."""

from pathlib import Path

from arb_mcp.application.convert_model import convert_source
from arb_mcp.domain.loading import load
from arb_mcp.domain.model import Model

FIX = Path(__file__).parent / "fixtures"
AGATHA = (FIX / "agatha.json").read_text("utf-8")
DSL = (FIX / "simple.dsl").read_text("utf-8")


def test_structurizr_round_trips() -> None:
    """canonical -> Structurizr DSL -> canonical keeps every C4 element."""
    original = load(AGATHA)
    dsl = convert_source(AGATHA, "structurizr")
    assert dsl.startswith("workspace")
    reloaded = load(dsl)  # must parse as valid Structurizr and survive the schema

    def c4_ids(m: Model) -> set[str]:
        return {
            n.id
            for n in m.walk()
            if n.type in {"person", "softwareSystem", "container", "component"}
        }

    # every C4 element in the source survives the trip
    assert c4_ids(original) <= c4_ids(reloaded)


def test_structurizr_has_views_per_level() -> None:
    dsl = convert_source(DSL, "structurizr")
    assert "systemLandscape" in dsl
    assert "container sys" in dsl  # C2 view for the system with a container


def test_structurizr_carries_technology() -> None:
    dsl = convert_source(DSL, "structurizr")
    assert "TypeScript" in dsl  # the container's technology
    assert "HTTPS" in dsl  # the relation's technology
