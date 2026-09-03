"""Vendored engine — ported verbatim from the DSL reference implementation.

Bit-for-bit equivalent to Structurizr on the measured corpus (16=16 elements,
20=20 relations, 3=3 views). It works on plain dicts by design: the schema is
normative, not the Python types. Do not rewrite it to satisfy a linter; it is
fenced out of ruff and mypy on purpose. The typed facade lives one level up.
"""
