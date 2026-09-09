# Multi-stage: build the wheel with a full toolchain, run it on a slim image as
# non-root. Only the HTTP adapter is a deployable; stdio runs on the architect's
# laptop. The base image is pinned by DIGEST, not by tag, so the same Dockerfile
# builds the same bytes next month; bump the digest on purpose, never by accident.
ARG BASE=python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285

FROM ${BASE} AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip build \
 && python -m build --wheel --outdir /dist \
 && pip wheel --no-cache-dir --wheel-dir /wheels "/dist/$(ls /dist)[http]"

FROM ${BASE} AS runtime
ARG VERSION=0.0.0
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="arb-mcp" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/EfrainGaray/arb-mcp" \
      org.opencontainers.image.description="Deterministic C4/DSL validation, conversion and catalog reconciliation"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ARB_HTTP_HOST=0.0.0.0 ARB_HTTP_PORT=8000
RUN groupadd --system arb && useradd --system --gid arb --no-create-home arb
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels arb-mcp[http] && rm -rf /wheels
USER arb
EXPOSE 8000
# No curl on slim: probe with the interpreter that is already there.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
# Authentication is configured at run time (ARB_OIDC_* or ARB_HTTP_TOKEN); the
# image refuses to start without it.
CMD ["arb-mcp-http"]
