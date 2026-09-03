"""Ports: the interfaces the core needs from the outside world.

Kept as ``Protocol`` so infra adapters (Jira, an LLM, drawio) are structural
implementations with no import back into application. The deterministic core —
loading and linting — needs none of these; they exist for the non-blocking
edges (generate from an epic, render a diagram) so that nothing probabilistic
can ever be wired into the validation path by accident.
"""
from __future__ import annotations

from typing import Any, Protocol


class LlmPort(Protocol):
    """Drafts the variable part of a design from natural language.

    Returns only ``nodes``/``relations``/``views`` — never the ``spec``. The
    spec (the type system) is fixed and supplied by the use case, so the model
    cannot invent its own types and the output is always checkable against a
    known contract."""

    def draft_design(self, description: str, stories: list[str]) -> dict[str, Any]: ...


class JiraPort(Protocol):
    def fetch_epic(self, key: str) -> tuple[str, list[str]]: ...


class DrawioPort(Protocol):
    def render(self, xml: str) -> str: ...
