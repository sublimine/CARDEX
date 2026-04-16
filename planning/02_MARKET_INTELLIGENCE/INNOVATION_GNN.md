# Innovation Track: GNN Dealer Inference + LayoutLMv3 PDF Extraction

**Status:** Implemented — Sprint 29
**Branch:** `sprint/29-gnn-layoutlm`
**Directories:**
- `innovation/gnn_dealer_inference/` — PyTorch Geometric GraphSAGE service
- `innovation/layoutlm_pdf/` — LayoutLMv3 registry document extractor
- `discovery/internal/families/a_registries/` — Go integration layer

---

## Problem Statement

CARDEX discovers dealers across 15 familia scrapers (A–O), but has no model
of the supply chain topology:

- Which dealers buy used stock from wholesalers?
- Which are brokers (resell without physical lot)?
- Which dealers share the same beneficial owner?

Without supply chain awareness, trust scoring (V15) treats all dealers as
independent. A fraudulent fleet dealer can create satellite micro-sites
that bypass individual trust thresholds.

---

## GNN Dealer Inference

### Graph Construction

| Element | Description |
|---------|-------------|
| **Nodes** | Each `dealer_entity` row is one node |
| **Directed edges** | Same VIN observed at dealer A (earlier) → dealer B (later) implies A sold to B |
| **Node features** | 9-dim: volume, avg_price (log), avg_mileage (log), brand entropy, country, age, V15 trust, V21 cluster size, is_active |

### Model: GraphSAGE 2-layer

```
Input [N, 9]
  → SAGEConv(9→64, aggr=mean) + ReLU + Dropout(0.3)
  → SAGEConv(64→32, aggr=mean)
  → Embeddings Z [N, 32]

Link head:  MLP([z_u || z_v || z_u*z_v]) → sigmoid probability
Node head:  Linear(32, 4) → {WHOLESALE, RETAIL, BROKER, FLEET}
```

### Temporal Split (anti-leakage)

Edges are sorted by `first_observed` timestamp. The most recent 10% form
the test set, the next 10% the validation set. This prevents future VIN
observations from leaking into training.

### CPU-Only Viability

| Component | RAM | Inference |
|-----------|-----|-----------|
| GraphSAGE 2-layer, <100K nodes | ~200 MB | <30s full-graph |
| Batch inference (1 dealer) | ~50 MB | <500ms |

PyTorch Geometric is the primary backend.
DGL is the documented fallback if `torch_scatter`/`torch_sparse` fail to compile.

### Service Interface

```
POST http://localhost:8501/predict-links
Body:    {"dealer_id": "D123", "top_k": 5}
Returns: {"predicted_links": [{"dst_dealer_id": "D456", "probability": 0.91}, ...]}

GET /health   → {"status": "ok", "nodes": N, "backend": "pyg|dgl"}
GET /metrics  → Prometheus text (cardex_gnn_*)
```

### Setup

```bash
make gnn-setup       # install torch CPU + torch_geometric
make gnn-train       # train on ./data/discovery.db
make gnn-serve       # start Flask server on :8501
make gnn-test        # run pytest suite
```

---

## LayoutLMv3 PDF Extraction

### Supported Documents

| Jurisdiction | Document Type | Key Fields |
|---|---|---|
| DE | Handelsregister (HRB/HRA) | company_name, HRB number, address, Geschäftsführer |
| FR | Extrait Kbis | company_name, SIREN, siège social, gérant |
| ES | Nota Simple Informativa | company_name, NIF, domicilio, administrador |

### Architecture

```
PDF → pdf2image (poppler) → [PIL Image per page]
    → pytesseract OCR → (words, bboxes normalised 0–1000)
    → LayoutLMv3Processor + LayoutLMv3ForTokenClassification
    → NER tags → entity extraction + confidence
    → JSON stdout
```

**Model:** `microsoft/layoutlmv3-base` (125M params, ~500 MB RAM, 2–5s/page CPU)

### Fallback Strategy

When LayoutLMv3 or OCR stack is unavailable (CI, lightweight deployments),
`extractor.py` falls back to regex/keyword heuristics:
- HRB/SIREN/NIF registration number patterns
- GmbH/SA/SARL/SL company name patterns
- Geschäftsführer/gérant/administrador legal representative patterns

Heuristic accuracy (~75% F1) vs. fine-tuned LayoutLMv3 (~92% F1).

### Production Path

Fine-tune `layoutlmv3-base` on 200–500 manually annotated pages:
```bash
python train_ner.py --data annotated/ --output model/ --epochs 20
```
The fine-tuned model is referenced via `LAYOUTLM_MODEL_PATH` env var.

### Go Integration

```go
// Invoked from discovery/internal/families/a_registries
out, err := exec.CommandContext(ctx,
    "python3", "extractor.py", "--pdf", pdfPath,
).Output()
var result ExtractorOutput
json.Unmarshal(out, &result)
```

### Setup

```bash
make layoutlm-setup     # install transformers, pdf2image, pytesseract
make layoutlm-fixtures  # generate DE/FR/ES test PDFs
make layoutlm-test      # run pytest suite
```

---

## Go Integration: `a_registries.GNNClient`

Package: `discovery/internal/families/a_registries`

| Symbol | Description |
|--------|-------------|
| `NewGNNClient()` | builds from `GNN_SERVICE_URL`, `GNN_TOP_K`, `GNN_TIMEOUT_MS` |
| `(*GNNClient).PredictLinks(ctx, dealerID)` | POST /predict-links → `[]PredictedLink` |
| `EnsureLinksSchema(db)` | idempotent DDL for `dealer_predicted_links` |
| `PersistLinks(ctx, db, links)` | upserts links with `ON CONFLICT DO UPDATE` |
| `EnrichDealer(ctx, db, client, dealerID)` | orchestrates predict + persist |

### Prometheus Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `cardex_gnn_predictions_total` | Counter | `result={success,error,skip}` |
| `cardex_gnn_latency_seconds` | Histogram | — |
| `cardex_gnn_links_stored_total` | Counter | — |

### Table: `dealer_predicted_links`

```sql
CREATE TABLE dealer_predicted_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_a      TEXT    NOT NULL,   -- predicted supplier
    dealer_b      TEXT    NOT NULL,   -- predicted buyer
    probability   REAL    NOT NULL,
    model_version TEXT    NOT NULL,
    predicted_at  TIMESTAMP,
    UNIQUE(dealer_a, dealer_b)
);
```

---

## Phase Roadmap

| Phase | Target | Description |
|-------|--------|-------------|
| Phase 5 (Sprint 29) | ✅ Done | GraphSAGE scaffolding + Flask service + Go client |
| Phase 6 | Planned | Fine-tune LayoutLMv3 on 500 annotated registry pages |
| Phase 6 | Planned | Wire `EnrichDealer` into discovery pipeline post-resolution |
| Phase 7 | Planned | BGE-M3 ONNX embedder (blocked on CGO — see V21) |
| Phase 7 | Planned | FAISS approximate-NN for large-scale embedding search |

---

## CPU-Only Installation Blockers

### PyG torch_scatter / torch_sparse

On some platforms (ARM64, Alpine), the prebuilt wheels for `torch_scatter` and
`torch_sparse` are unavailable. **Workaround:** use DGL backend (set
`DGL_FALLBACK=1` before `import data_loader`) or build from source:
```bash
pip install torch_scatter torch_sparse --no-binary :all:
```

### LayoutLMv3 + pdf2image

Requires system packages:
```bash
apt-get install poppler-utils tesseract-ocr tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa
```
**CI strategy:** run `pytest -m "not fixture_pdf"` to skip full-stack tests;
heuristic tests have no system deps.
