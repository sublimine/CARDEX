# syntax=docker/dockerfile:1
# CARDEX Chronos-2 forecasting — Chronos-bolt-mini + statsforecast fallback (CPU-only)
# Multi-stage: CPU-only torch + deps in a builder venv; lean non-root runtime.

# ── Stage 1: build dependency venv ───────────────────────────────
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first (chronos-forecasting pulls torch transitively otherwise
# it would fetch the multi-GB CUDA build).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    TIMESERIES_DIR=/data/timeseries \
    FORECAST_PORT=8503 \
    CHRONOS_MODEL=amazon/chronos-bolt-mini

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /usr/sbin/nologin appuser \
    && mkdir -p /app /data/timeseries \
    && chown -R appuser:appuser /app /data

COPY --chown=appuser:appuser . /app
WORKDIR /app
USER appuser

VOLUME ["/data/timeseries"]
EXPOSE 8503

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8503/health', timeout=5)"]

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8503"]
