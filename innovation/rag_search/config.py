"""Central configuration for CARDEX RAG search service."""

from __future__ import annotations

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

RAG_DATA_DIR = Path(os.getenv("RAG_DATA_DIR", "data/rag"))
FAISS_INDEX_PATH = RAG_DATA_DIR / "faiss_index.bin"
ID_MAP_PATH = RAG_DATA_DIR / "id_map.json"
CARDEX_DB_PATH = Path(os.getenv("CARDEX_DB_PATH", "data/discovery.db"))

# ── Embedding model ───────────────────────────────────────────────────────────

EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")
EMBED_DIM = int(os.getenv("RAG_EMBED_DIM", "768"))
EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "64"))
EMBED_MAX_TOKENS = int(os.getenv("RAG_EMBED_MAX_TOKENS", "256"))

# Document prefix required by nomic-embed-text-v1.5 for asymmetric retrieval.
EMBED_DOC_PREFIX = "search_document: "
EMBED_QUERY_PREFIX = "search_query: "

# ── FAISS index ───────────────────────────────────────────────────────────────

# IVF-Flat: nlist=100 cells, suitable for up to ~1M vectors.
# Falls back to Flat for datasets smaller than nlist * 39 (FAISS training min).
FAISS_NLIST = int(os.getenv("RAG_FAISS_NLIST", "100"))
FAISS_NPROBE = int(os.getenv("RAG_FAISS_NPROBE", "10"))  # cells searched at query time

# ── Query defaults ────────────────────────────────────────────────────────────

QUERY_TOP_K_FAISS = int(os.getenv("RAG_TOP_K_FAISS", "50"))   # FAISS candidates
QUERY_TOP_K_RETURN = int(os.getenv("RAG_TOP_K_RETURN", "20"))  # returned to caller

# ── LLM reranker ──────────────────────────────────────────────────────────────

LLM_RERANK_ENABLED = os.getenv("RAG_LLM_RERANK", "false").lower() == "true"
LLM_MODEL_PATH = os.getenv(
    "RAG_LLM_MODEL_PATH",
    "models/llama-3.2-3b-instruct.Q4_K_M.gguf",
)
LLM_N_CTX = int(os.getenv("RAG_LLM_N_CTX", "4096"))
LLM_N_THREADS = int(os.getenv("RAG_LLM_N_THREADS", "4"))

# ── API server ────────────────────────────────────────────────────────────────

API_HOST = os.getenv("RAG_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("RAG_API_PORT", "8502"))
API_RATE_LIMIT = int(os.getenv("RAG_RATE_LIMIT_PER_MIN", "100"))
