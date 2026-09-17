"""Use case: export a canonical model to a text surface.

Every surface is an exporter over the same model the linter validates, so a
diagram and its verdict cannot drift. drawio is emitted as SEPARATE C4 views
(C1, one C2 per system, one C3 per container) — never one file with tabs —
because C4 is a set of diagrams, not a canvas.
"""

from __future__ import annotations

import json
from typing import Any

from ..domain import drawio, loading, mermaid, structurizr
from ..domain.model import Model

FORMATS = ("drawio", "structurizr", "mermaid")


def drawio_views(model: Model) -> list[dict[str, Any]]:
    """The C4 views as independent diagrams: level, scope, name, standalone xml."""
    return [d.to_dict() for d in drawio.to_views(model)]


def convert_model(model: Model, fmt: str) -> str:
    """Export ``model`` as ``fmt``.

    - ``drawio``      JSON object with the list of separate C4 views (C1/C2/C3).
    - ``structurizr`` Raw Structurizr DSL text.
    - ``mermaid``     JSON object with the list of Mermaid C4 views (C4 models only).
    """
    if fmt == "drawio":
        return json.dumps({"views": drawio_views(model)}, ensure_ascii=False, indent=2)
    if fmt == "structurizr":
        return structurizr.to_structurizr(model)
    if fmt == "mermaid":
        return json.dumps(
            {"views": [d.to_dict() for d in mermaid.to_c4_views(model)]},
            ensure_ascii=False,
            indent=2,
        )
    raise ValueError(f"unknown format {fmt!r}; known: {', '.join(FORMATS)}")


def convert_source(text: str, fmt: str) -> str:
    """Load ``text`` (any accepted surface) then export it as ``fmt``.

    The Structurizr-DSL-to-drawio path the bank needs: load the DSL it already
    has, hold it to the schema, emit native C4 drawio views."""
    model = loading.load(text)
    return convert_model(model, fmt)
