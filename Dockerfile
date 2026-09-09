# Multi-stage: build wheels with a full toolchain, run on a slim image as non-root.
# Only the HTTP adapter is a deployable; stdio runs on the architect's laptop.

FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip wheel \
 && pip wheel --no-cache-dir --wheel-dir /wheels ".[http]"

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ARB_HTTP_HOST=0.0.0.0 ARB_HTTP_PORT=8000
RUN groupadd --system arb && useradd --system --gid arb --no-create-home arb
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER arb
EXPOSE 8000
# No curl on slim: probe with the interpreter that is already there.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
# ARB_HTTP_TOKEN must be supplied at run time; the image refuses to start without it.
CMD ["arb-mcp-http"]
