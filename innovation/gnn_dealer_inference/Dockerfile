# syntax=docker/dockerfile:1
# CARDEX GNN dealer inference — GraphSAGE link prediction (CPU-only)
# Multi-stage: CPU-only torch + deps in a builder venv; lean non-root runtime.

# ── Stage 1: build dependency venv ───────────────────────────────
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first (avoids pulling multi-GB CUDA wheels), then the rest.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Optional accelerators — may be unavailable for some torch builds; DGL fallback
# handles their absence at runtime, so a failure here must not break the build.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pyg_lib torch_scatter torch_sparse \
      -f https://data.pyg.org/whl/torch-$(python -c "import torch; print(torch.__version__.split('+')[0])")+cpu.html \
    || echo "WARNING: torch_scatter/torch_sparse unavailable — using DGL fallback"

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    GNN_PORT=8501

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlite3-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /usr/sbin/nologin appuser \
    && mkdir -p /app \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . /app
WORKDIR /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/health', timeout=5)"]

CMD ["python", "serve.py"]
