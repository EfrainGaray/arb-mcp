"""Use case: export a canonical model to a text surface.

Every surface is an exporter over the same model the linter validates — so a
diagram and its verdict cannot drift. drawio is the one the bank consumes;
``.arch`` is the human-readable DSL. Mermaid and Structurizr are declared but
not yet wired, and say so loudly rather than returning something half-made.
"""
from __future__ import annotations

from typing import Any

from ..domain import drawio, loading
from ..domain._engine import convert as _arch

FORMATS = ("drawio", "arch")


def convert_model(model: dict[str, Any], fmt: str) -> str:
    if fmt == "drawio":
        return drawio.to_drawio(model)
    if fmt == "arch":
        arch: str = _arch.json_to_text(model)
        return arch
    raise ValueError(f"unknown format {fmt!r}; known: {', '.join(FORMATS)}")


def convert_source(text: str, fmt: str) -> str:
    """Load ``text`` (any accepted surface) then export it as ``fmt``.

    This is the Structurizr-DSL-to-drawio path the bank needs: load the DSL it
    already has, hold it to the schema, emit native C4 drawio XML.
    """
    model = loading.load(text)
    return convert_model(model, fmt)
