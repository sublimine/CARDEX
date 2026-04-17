# INNOVATION_RAG — Local RAG Search (Sprint 30)

**Status:** DELIVERED — Sprint 30  
**Branch:** `sprint/30-rag-search`  
**Directory:** `innovation/rag_search/`

---

## Overview

Natural-language search over the CARDEX vehicle inventory using a fully local
RAG stack: nomic-embed-text-v1.5 for embeddings, FAISS for approximate nearest
neighbour retrieval, and an optional Llama 3.2 3B Q4 reranker.

A buyer writes:

> "busco BMW Serie 3 diesel menos de 100.000 km por debajo de 20.000€ en Alemania o Países Bajos"

The system returns listings ranked by semantic relevance, with hard filters
applied post-retrieval.

---

## Architecture

```
SQLite (vehicle_record)
        │
        ▼
  indexer.py  ──────  nomic-embed-text-v1.5  ──────  FAISS IVF-Flat
   (cron/24h)           (137M, 768 dims)             faiss_index.bin
                                                       id_map.json
                                                            │
                                                            │
User query (CLI / API)                                      │
        │                                                   │
        ▼                                                   │
query_engine.py ── embed query ──────────────────── top-50 ANN search
        │
        ├─ hard filters (country, price, km, year, fuel)
        │
        ├─ (optional) llm_reranker.py  (Llama 3.2 3B Q4, RAG_LLM_RERANK=true)
        │
        ▼
   top-20 results
        │
   ┌────┴──────────────────────────┐
   │                               │
serve.py (FastAPI :8502)    cardex search-natural (Go CLI)
POST /search                fallback: SQL keyword search
GET  /health
```

---

## Components

### `config.py`
Central configuration. All parameters are overridable via environment variables.

Key variables:
- `CARDEX_DB_PATH` — path to SQLite database (default: `data/discovery.db`)
- `RAG_DATA_DIR` — directory for FAISS index files (default: `data/rag`)
- `RAG_EMBED_MODEL` — HuggingFace model ID (default: `nomic-ai/nomic-embed-text-v1.5`)
- `RAG_LLM_RERANK` — enable Llama reranker (`true`/`false`, default `false`)
- `RAG_API_PORT` — FastAPI port (default `8502`)

### `indexer.py`
Reads all non-rejected `vehicle_record` rows from SQLite. Builds a text
representation per listing (make + model + year + mileage + fuel + price +
country) and embeds it with nomic-embed-text using the `search_document:` prefix.

Embeddings are normalised (L2) to enable cosine similarity via inner product.
The FAISS index uses IVF-Flat (nlist=100) for datasets ≥ 3,900 vectors;
falls back to IndexFlatIP for smaller test datasets.

**Incremental update:** `--incremental` flag skips IDs already in `id_map.json`.
Full re-index is recommended every 24h (cron); incremental every 1h.

### `query_engine.py`
Embeds the query with the `search_query:` prefix → FAISS top-50 ANN search
→ fetches listing metadata from SQLite → applies hard filters → returns
top-20 as `SearchResult` dataclasses.

Hard filters applied post-retrieval: country, price_min, price_max, km_max,
year_min, year_max, fuel_type.

### `llm_reranker.py`
Opt-in. Uses Llama 3.2 3B (Q4_K_M GGUF) via llama-cpp-python. Sends a
structured prompt asking the model to score 0–10 each candidate listing
against the buyer's query. Results are re-sorted by LLM score.

- RAM: ~2 GB (Q4 quantised)
- Latency: ~5–10s on 4-core CPU
- Model file: `models/llama-3.2-3b-instruct.Q4_K_M.gguf`

Not installed by default; add `llama-cpp-python` to requirements and set
`RAG_LLM_RERANK=true` to enable.

### `serve.py`
FastAPI application exposed on port 8502.

**Endpoints:**
- `POST /search` — natural-language search
  ```json
  {"query": "BMW diesel Germany", "filters": {"country": "DE", "price_max": 25000}, "top_k": 20}
  ```
- `GET /health` — index status: vector count, last_indexed_at, uptime
- `POST /reload` — hot-reload the FAISS index after incremental update

Rate limit: 100 requests/min (slowapi).

---

## Go CLI Integration

**Subcommand:** `cardex search-natural <query> [flags]`

```
cardex search-natural "BMW Serie 3 diesel menos de 100000 km" --country DE --price-max 20000
```

The CLI calls `POST /search` on the RAG server. Results are displayed in an
ANSI table identical to `cardex search` output.

**Fallback:** If the RAG server is unavailable (connection refused / timeout),
the CLI automatically falls back to a SQL keyword search using tokenised words
from the query as LIKE patterns against `make_canonical` and `model_canonical`.

Environment variable: `CARDEX_RAG_URL` (default: `http://localhost:8502`).

---

## Deployment — Hetzner CX42 (CPU-only)

| Component               | RAM     | Notes                                  |
|-------------------------|---------|----------------------------------------|
| nomic-embed-text-v1.5   | ~600 MB | 137M params, 768 dims                  |
| FAISS index (100K × 768)| ~300 MB | IVF-Flat, 32-bit float                 |
| FastAPI + workers       | ~150 MB | Uvicorn 1 worker process               |
| Llama 3.2 3B Q4 (opt-in)| ~2 GB   | Only loaded when RAG_LLM_RERANK=true   |
| **Total (no LLM)**      | ~1.1 GB | Well within 16 GB CX42 RAM budget      |

Indexing speed: ~50ms/embedding × 100K listings ≈ 80 min full re-index.
Viable as a nightly cron; incremental hourly.

Query latency: ~50ms embedding + <10ms FAISS search = ~60ms end-to-end.

---

## Cron Schedule (recommended)

```cron
# Full re-index at 02:00 UTC every night
0 2 * * * cd /app/innovation/rag_search && python indexer.py >> /var/log/rag-index.log 2>&1

# Incremental update every hour
30 * * * * cd /app/innovation/rag_search && python indexer.py --incremental >> /var/log/rag-index.log 2>&1
```

---

## Testing

```bash
# Unit tests (mocked embedding model — no network, no GPU required)
make rag-test

# Or directly:
cd innovation/rag_search && python -m pytest tests/ -v
```

Tests:
- `test_indexer.py` — full index, incremental, id_map coverage, text builder
- `test_query.py` — FAISS search, country/price/km filters, empty index
- `test_reranker.py` — LLM score parsing, ordering, error handling

---

## Open BLOCKERs

| Item | Status |
|------|--------|
| UTAC CT dataset ID verification (I.FR.2) | BLOCKER — verify at data.economie.gouv.fr |
| ITV ArcGIS URL (I.ES.1) | BLOCKER — DevTools on DGT locator |
| AUTOSÉCURITÉ + GOCA API URLs (I.BE.1) | BLOCKER — DevTools on autosecurite.be / keuringplus.be |
| Llama 3.2 GGUF model file | Not shipped — download from huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF |

---

## Future Work

- Multilingual query expansion (translate ES/FR/DE → EN before embedding)
- Metadata filtering as FAISS pre-filter (IDMap + pre-filter bitmap)
- Hybrid retrieval: BM25 + dense, merged via Reciprocal Rank Fusion
- Fine-tuned embedding model on CARDEX listing pairs
