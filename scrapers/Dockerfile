# syntax=docker/dockerfile:1
# Dockerfile — CARDEX scraper fleet (Strategy B: curl_cffi + Camoufox)
# Multi-stage: deps compiled in a builder venv, browsers + runtime only in final.
#
# Build context is the scrapers/ directory (see root docker-compose.yml).
# The package is imported as `scrapers.*` (e.g. `from scrapers.db import ...`),
# so the context is copied into /app/scrapers and PYTHONPATH=/app.
# Entry point: python -m scrapers.coordinator  (the verified orchestrator).

# ── Stage 1: build dependency venv ───────────────────────────────
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential covers any source-only wheels; it never reaches the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# tini = proper PID1 (reaps zombie browser processes); ca-certificates for TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Chromium (Playwright) + its OS dependencies. Camoufox's Firefox is fetched
# below as the non-root user so it lands in that user's cache.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /usr/sbin/nologin appuser \
    && mkdir -p /app /ms-playwright \
    && chown -R appuser:appuser /app /ms-playwright

# Application code → /app/scrapers so `import scrapers.*` resolves under PYTHONPATH=/app.
COPY --chown=appuser:appuser . /app/scrapers

USER appuser
WORKDIR /app

# Fetch Camoufox's patched Firefox (approved Strategy B anti-detect engine).
RUN python -m camoufox fetch

ARG VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="cardex-scrapers" \
      org.opencontainers.image.description="CARDEX marketplace scraper fleet (Strategy B)" \
      org.opencontainers.image.source="https://github.com/cardex/cardex" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="UNLICENSED"

# Liveness smoke test: the coordinator module imports the full engine (db,
# identity, router, monitoring) WITHOUT pulling curl_cffi/asyncpg/redis or
# touching the network (guaranteed by its module contract), so a clean import
# proves the venv, package layout and dependencies are intact.
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import scrapers.coordinator"]

# ENTRYPOINT runs python under tini; compose passes `-m scrapers.coordinator`
# (or another `-m <module>`) via `command:`.
ENTRYPOINT ["/usr/bin/tini", "--", "python"]
CMD ["-m", "scrapers.coordinator"]
