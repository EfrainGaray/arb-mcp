"""Use case: export a canonical model to a text surface.

Every surface is an exporter over the same model the linter validates, so a
diagram and its verdict cannot drift. drawio is emitted as SEPARATE C4 views
(C1, one C2 per system, one C3 per container) — never one file with tabs —
because C4 is a set of diagrams, not a canvas.
"""
from __future__ import annotations

import json
from typing import Any

from ..domain import drawio, loading, structurizr

FORMATS = ("drawio", "structurizr")


def drawio_views(model: dict[str, Any]) -> list[dict[str, Any]]:
    """The C4 views as independent diagrams: level, scope, name, standalone xml."""
    return drawio.to_views(model)


def convert_model(model: dict[str, Any], fmt: str) -> str:
    """Export ``model`` as ``fmt``. For drawio, returns a JSON object with the
    list of separate C4 views."""
    if fmt == "drawio":
        return json.dumps({"views": drawio_views(model)}, ensure_ascii=False, indent=2)
    if fmt == "structurizr":
        return structurizr.to_structurizr(model)
    if fmt == "arch":
        # Internal, unannounced surface: the canonical text language belongs to a
        # separate project, not to this deliverable. Left functional on explicit
        # request; deliberately absent from FORMATS and the error message.
        return loading.to_arch(model)
    raise ValueError(f"unknown format {fmt!r}; known: {', '.join(FORMATS)}")


def convert_source(text: str, fmt: str) -> str:
    """Load ``text`` (any accepted surface) then export it as ``fmt``.

    The Structurizr-DSL-to-drawio path the bank needs: load the DSL it already
    has, hold it to the schema, emit native C4 drawio views."""
    model = loading.load(text)
    return convert_model(model, fmt)
