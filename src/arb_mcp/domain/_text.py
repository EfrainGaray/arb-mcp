"""Shared string-folding utilities for notation exporters.

Both ``structurizr.py`` and ``mermaid.py`` need to fold double-quotes and
newlines in model strings before embedding them in quoted string literals.
Defined once here so the two exporters cannot drift from each other.
"""

from __future__ import annotations


def fold_quotes(text: str) -> str:
    """Fold characters that are structurally significant in quoted string
    literals (Mermaid C4, Structurizr DSL) to safe surrogates:

    - ``"``  →  ``'``  (both notations have no string-escape syntax)
    - ``\\n``, ``\\r``  →  ``" "``  (a newline inside a quoted arg corrupts the line)

    The transformation is lossy but legible and guarantees round-trip safety.
    """
    return str(text).replace('"', "'").replace("\n", " ").replace("\r", " ")
