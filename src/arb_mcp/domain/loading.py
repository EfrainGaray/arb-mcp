"""Load a canonical model from any accepted surface, then hold it to the schema.

Three inputs are accepted and all collapse to the same canonical model dict:
the ``.arch`` language, the schema JSON directly, and Structurizr DSL. Format is
detected, never guessed from a flag the caller might get wrong. Whatever the
surface, the result is validated against the normative schema before it is
allowed to leave this module: a model that does not survive the schema does not
exist as far as the rest of the system is concerned.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

import jsonschema

from ._engine import convert, from_structurizr

SCHEMA: dict[str, Any] = json.loads(
    (files("arb_mcp.domain._engine.schema") / "architecture.schema.json").read_text("utf-8")
)


class ModelError(ValueError):
    """The input could not be turned into a schema-valid canonical model."""


def _looks_like_json(text: str) -> bool:
    return text.lstrip().startswith("{")


_STRUCTURIZR_HEAD = re.compile(r"\s*(//[^\n]*\n\s*)*workspace\b")


def _looks_like_structurizr(text: str) -> bool:
    """Structurizr DSL opens with ``workspace``; ``.arch`` opens with ``model``.
    Anchored at the start so a stray "workspace" inside a free-text description
    of an ``.arch`` file no longer hijacks the format detection."""
    return _STRUCTURIZR_HEAD.match(text) is not None


def load(text: str) -> dict[str, Any]:
    """Parse ``text`` (``.arch`` / schema JSON / Structurizr DSL) into a
    validated canonical model."""
    model: dict[str, Any]
    try:
        if _looks_like_json(text):
            model = json.loads(text)
        elif _looks_like_structurizr(text):
            model, _lost = from_structurizr.convert(text)
        else:
            model = convert.text_to_json(text)
    except ModelError:
        raise
    except Exception as exc:  # parse errors from lark / json / the converter
        raise ModelError(str(exc)) from exc

    validate_schema(model)
    _check_depth(model.get("nodes", []))
    return model


_MAX_DEPTH = 32


def _check_depth(nodes: list[dict[str, Any]], depth: int = 1) -> None:
    """Bound nesting so agent-generated input cannot blow the recursion limit in
    the exporters. Deep enough for any real architecture, shallow enough to fail
    as a ModelError instead of a raw RecursionError."""
    if depth > _MAX_DEPTH:
        raise ModelError(f"model nesting exceeds {_MAX_DEPTH} levels")
    for n in nodes:
        _check_depth(n.get("nodes", []), depth + 1)


def validate_schema(model: dict[str, Any]) -> None:
    """Raise :class:`ModelError` unless ``model`` satisfies the normative schema."""
    try:
        jsonschema.validate(model, SCHEMA)
    except jsonschema.ValidationError as exc:
        loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ModelError(f"schema: {loc}: {exc.message}") from exc


def to_arch(model: dict[str, Any]) -> str:
    """Emit the canonical text (``.arch``) surface. Facade over the engine so no
    caller reaches into ``_engine`` directly."""
    text: str = convert.json_to_text(model)
    return text
