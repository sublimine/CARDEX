# V21 — Multilingual Dealer Entity Resolution

**Status:** Implemented — Sprint 25  
**Package:** `cardex.eu/quality/internal/validator/v21_entity_resolution`  
**Severity:** INFO (enrichment only — does not gate publication)  
**Priority:** Runs after V20 (composite scorer)

---

## Purpose

Multiple discovery sources (Familia A–O) observe the same physical dealer
under different name and address representations:

| Source | Name variant |
|--------|-------------|
| mobile.de | BMW Autohaus GmbH München |
| Handelsregister | Autohaus München BMW GmbH |
| OSM | Autohaus München GmbH |

V21 resolves these variants to a single canonical entity ID by embedding the
dealer text (name + city + country) into a shared vector space and comparing
with cosine similarity. Matches above the configured threshold are merged under
the earliest-seen entity ID.

---

## Embedding Backends

Two backends implement the `TextEmbedder` interface:

### 1. TFIDFEmbedder (pure Go — default)

- Character 3-gram TF hashing, 256-dimensional sparse vector
- No external dependencies — runs on any platform without CGO
- Accuracy: adequate for same-dealer name normalisation (tested threshold 0.75)
- Used in tests and as production fallback when Python is unavailable

### 2. SubprocessEmbedder (Python mpnet — production)

- Model: `paraphrase-multilingual-mpnet-base-v2` (278M params, 768-dim)
- Supports 50+ languages natively — covers DE/FR/ES/NL/BE/CH market
- Requires: `pip install sentence-transformers torch`
- Enabled via env var: `QUALITY_V21_PYTHON=python3`
- Accuracy: high — recommended threshold 0.85 (default)

### BGE-M3 (roadmap — Phase 5+)

BGE-M3 (568M, 1024-dim) is the target embedder for production accuracy.
**Blocked on:** `onnxruntime-go` requires CGO and is unstable for
CPU-only linux/amd64 cross-compilation.  
Tracked as `TODO(V21-ONNX)` in `embedder.go`.

---

## Embedding Index

Embeddings are persisted in the shared SQLite knowledge graph under the
`entity_embeddings` table:

```sql
CREATE TABLE IF NOT EXISTS entity_embeddings (
    entity_id     TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    embedding     BLOB NOT NULL,   -- float32 little-endian
    dim           INTEGER NOT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Search strategy:** full linear scan with cosine similarity comparison.
Acceptable for the current scale (tens of thousands of dealer entities).
Phase 5: replace with approximate nearest-neighbour index (FAISS or hnswlib
via CGO once CGO is available in the build pipeline).

---

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `QUALITY_SKIP_V21` | `false` | Disable V21 entirely |
| `QUALITY_V21_THRESHOLD` | `0.85` | Cosine similarity threshold (0–1] |
| `QUALITY_V21_PYTHON` | `""` | Python binary for mpnet embedder |

---

## Output

V21 produces a `ValidationResult` with `Severity=INFO` and `Pass=true`.
Evidence and suggestions are populated as follows:

| Field | Value |
|-------|-------|
| `Evidence["embedder"]` | backend name (e.g. `tfidf-256`) |
| `Evidence["dealer_text"]` | text that was embedded |
| `Evidence["entity_status"]` | `"unique"` or `"merged"` |
| `Evidence["cosine_similarity"]` | similarity score (when merged) |
| `Evidence["canonical_dealer_id"]` | canonical entity ID (when merged) |
| `Suggested["canonical_dealer_id"]` | canonical entity ID (when merged) |

---

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `cardex_quality_entity_resolution_matches_total` | Counter | Total entity merges performed |
| `cardex_quality_entity_resolution_latency_seconds` | Histogram | Embedding + search latency per vehicle |

---

## Test Coverage

| Test | Description |
|------|-------------|
| `TestV21_SameEntity_DE` | BMW Autohaus GmbH München ≃ Autohaus München BMW GmbH |
| `TestV21_SameEntity_FR` | Garage Renault Lyon Centre ≃ Renault Lyon Centre Garage |
| `TestV21_SameEntity_ES` | Seat Concesionario Madrid Sur ≃ Concesionario Madrid Sur SEAT |
| `TestV21_DifferentEntities_NotMerged` | BMW Autohaus Berlin ≠ BMW Autohaus Hamburg (threshold 0.92) |
| `TestV21_NilDB_NoIndex` | No-op graceful handling when no DB is wired |
| `TestTFIDFEmbedder_CosineSimilarity` | Same-dealer similarity > different-dealer similarity |
| `TestV21_Priority` | ID()="V21", Severity()="INFO" |

---

## Integration

V21 is registered in `quality/cmd/quality-service/main.go` after V20, using
`store.DB()` to pass the `*sql.DB` connection to `NewWithDB`. On init failure
(e.g. schema migration error) V21 is gracefully skipped with a `WARN` log —
it never prevents the service from starting.

---

## Dealer Text Construction

```
<DealerID> <SourceCountry> <dealer_name> <dealer_city> [<dealer_address>]
```

All fields sourced from `pipeline.Vehicle`: `DealerID`, `SourceCountry`, and
`Metadata["dealer_name"]`, `Metadata["dealer_city"]`, `Metadata["dealer_address"]`.
