# arb-mcp — repo instructions

**Phase: `clean`.** Physical layers `domain/` / `application/` / `infra/` with no
cross-imports upward. Domain is framework-free.

- `domain/_engine/` is a **vendored, ported engine** (bit-for-bit equivalent to
  Structurizr on the measured corpus). It works on plain dicts by design and is
  exempt from ruff/mypy. Do not rewrite it to satisfy a linter. All new logic
  lives in the typed facade (`findings`, `loading`, `linter`) or above.
- **Only deterministic validation may block a merge.** Generation from an epic is
  probabilistic and always non-blocking; nothing probabilistic may reach the
  `may_merge` verdict.
- Bug = failing test first, then fix. Gates before commit: `pytest`, `ruff check
  src/`, `mypy`.
