# The gates, as commands any CI can run. GitHub Actions and GitLab CI are both
# ten-line files that call `make ci`; the pre-commit hooks run the same targets.
# Nothing below knows which CI it is running in.
PY ?= python

.PHONY: install lint format typecheck test layers deps audit ci

install:
	$(PY) -m pip install --quiet --upgrade pip setuptools
	$(PY) -m pip install --quiet -e '.[http,dev]'

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy

test:
	$(PY) -m pytest -q

layers:
	lint-imports

deps:
	deptry src/
	$(PY) -m pip check

audit:
	pip-audit --progress-spinner off --skip-editable

ci: lint typecheck layers deps test audit
