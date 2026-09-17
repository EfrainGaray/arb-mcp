# arb-mcp — repo instructions

**Phase: `clean`.** Physical layers `domain/` / `application/` / `infra/` with no
cross-imports upward. Domain is framework-free.

- `domain/` is stdlib-only and fully typed. Key modules: `model.py` (frozen
  dataclasses), `loading.py` (schema validation + format detection + `CANONICAL_FORM`),
  `linter.py` + `inspections/` (deterministic rules), `implied.py`, `structurizr.py`,
  `c4_views.py` (notation-neutral C4 scoping), `drawio/` (package), `mermaid.py`,
  `_text.py` (shared text utilities). Nothing is vendored or exempt from ruff/mypy.
- **Only deterministic validation may block a merge.** Generation from an epic is
  probabilistic and always non-blocking; nothing probabilistic may reach the
  `may_merge` verdict.
- Bug = failing test first, then fix. Gates before commit: `pytest`, `ruff check
  src/`, `mypy`.
