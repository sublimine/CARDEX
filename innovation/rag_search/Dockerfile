# syntax=docker/dockerfile:1
# CARDEX RAG search — nomic-embed-text + FAISS + optional Llama reranker (CPU-only)
# Multi-stage: deps in a builder venv; runtime ships venv + model, no build tools.

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

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/home/appuser/.cache/huggingface \
    RAG_DATA_DIR=/app/data/rag \
    CARDEX_DB_PATH=/app/data/discovery.db \
    RAG_API_PORT=8502 \
    RAG_LLM_RERANK=false

# libgomp1 is the OpenMP runtime FAISS / sentence-transformers link against.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/models \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . /app
WORKDIR /app
USER appuser

# Pre-download nomic-embed-text at build time so the container starts fast.
# Cached under the appuser-owned HF_HOME.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

VOLUME ["/app/data", "/app/models"]
EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8502/health', timeout=5)"]

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8502"]
