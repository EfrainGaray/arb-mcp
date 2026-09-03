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
    def draft_model(self, epic: str, stories: list[str]) -> dict[str, Any]: ...


class JiraPort(Protocol):
    def fetch_epic(self, key: str) -> tuple[str, list[str]]: ...


class DrawioPort(Protocol):
    def render(self, xml: str) -> str: ...
