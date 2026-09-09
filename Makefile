# The gates, as commands any CI can run. GitHub Actions and GitLab CI are both
# ten-line files that call `make ci`; the pre-commit hooks run the same targets.
# Nothing below knows which CI it is running in.
PY ?= python
VERSION := $(shell $(PY) -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
VCS_REF := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
IMAGE   ?= arb-mcp
# Set REGISTRY (e.g. registry.gitlab.bank.cl/arch/arb-mcp or ghcr.io/org/arb-mcp)
# to push; empty means build and keep local.
REGISTRY ?=

.PHONY: install lint format typecheck test layers deps audit ci \
        build sbom image push checksums release version

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

# ── release: the same bytes from any CI ─────────────────────────────────────
version:
	@echo $(VERSION)

build:  ## wheel + sdist into dist/
	rm -rf dist && $(PY) -m build

sbom: build  ## CycloneDX SBOM of the runtime dependency set, next to the wheel
	$(PY) -m venv .sbom-env && .sbom-env/bin/pip install --quiet dist/*.whl 'arb-mcp[http]' --find-links dist \
	  && cyclonedx-py environment .sbom-env/bin/python --of JSON -o dist/arb_mcp-$(VERSION).cdx.json \
	  && rm -rf .sbom-env

image:  ## OCI image, tagged with the version and labelled with the commit
	docker build --build-arg VERSION=$(VERSION) --build-arg VCS_REF=$(VCS_REF) \
	  -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .

push: image
	@test -n "$(REGISTRY)" || (echo "REGISTRY is empty: nothing pushed" && exit 0)
	docker tag $(IMAGE):$(VERSION) $(REGISTRY):$(VERSION)
	docker push $(REGISTRY):$(VERSION)

checksums:  ## portable: no sha256sum on macOS
	cd dist && $(PY) -c "import hashlib,pathlib;print(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\\n' for p in sorted(pathlib.Path().iterdir()) if p.name!='SHA256SUMS'),end='')" > SHA256SUMS

release: build sbom checksums image  ## everything a reviewer needs, reproducibly
	@echo "release $(VERSION) ($(VCS_REF)): dist/ + $(IMAGE):$(VERSION)"
