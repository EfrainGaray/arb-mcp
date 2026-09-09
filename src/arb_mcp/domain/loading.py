"""Load a canonical model from an accepted surface, then hold it to the schema.

Two inputs are accepted and both collapse to the same typed ``Model``: the
canonical schema JSON, and Structurizr DSL (the surface the bank already
writes). Format is detected, never guessed from a flag the caller might get
wrong; anything else is refused as a ``ModelError`` instead of being fed to a
parser on a hunch. Whatever the surface, the dict is validated against the
normative schema before it becomes a ``Model``: a model that does not survive
the schema does not exist as far as the rest of the system is concerned.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

import jsonschema

from . import structurizr_dsl
from .model import Model

SCHEMA: dict[str, Any] = json.loads(
    (files("arb_mcp.domain.schema") / "architecture.schema.json").read_text("utf-8")
)


class ModelError(ValueError):
    """The input could not be turned into a schema-valid canonical model."""


def _looks_like_json(text: str) -> bool:
    return text.lstrip().startswith("{")


_STRUCTURIZR_HEAD = re.compile(r"\s*(//[^\n]*\n\s*)*workspace\b")


def _looks_like_structurizr(text: str) -> bool:
    """Structurizr DSL opens with ``workspace`` (comments allowed before it).
    Anchored at the start so a stray "workspace" inside a description elsewhere
    cannot hijack the format detection."""
    return _STRUCTURIZR_HEAD.match(text) is not None


def load(text: str) -> Model:
    """Parse ``text`` (schema JSON or Structurizr DSL) into a validated ``Model``."""
    raw: dict[str, Any]
    try:
        if _looks_like_json(text):
            raw = json.loads(text)
        elif _looks_like_structurizr(text):
            raw, _lost = structurizr_dsl.convert(text)
        else:
            raise ModelError(
                "unrecognized source: expected canonical JSON ('{') "
                "or Structurizr DSL ('workspace')"
            )
    except ModelError:
        raise
    except Exception as exc:  # parse errors from json / the converter
        raise ModelError(str(exc)) from exc
    return from_dict(raw)


def from_dict(raw: dict[str, Any]) -> Model:
    """Hold a dict to the schema and the nesting bound, then type it."""
    if not isinstance(raw, dict):
        raise ModelError("schema: <root>: the source is not a JSON object")
    validate_schema(raw)
    _check_depth(raw.get("nodes", []))
    return Model.from_dict(raw)


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
