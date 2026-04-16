"""
serve.py — Flask inference server for GNN dealer link prediction.

Endpoints
---------
POST /predict-links
    Body:  {"dealer_id": "D123", "top_k": 5}
    Returns: {"dealer_id": "D123", "predicted_links": [
                {"dst_dealer_id": "D456", "probability": 0.91},
                ...
              ]}

GET /health
    Returns: {"status": "ok", "nodes": N, "backend": "pyg|dgl"}

GET /metrics  (Prometheus text format)
    cardex_gnn_requests_total
    cardex_gnn_latency_seconds

Environment variables
---------------------
  GNN_MODEL_PATH  path to model.pt checkpoint   (default: model.pt)
  GNN_DB_PATH     path to SQLite KG             (default: ./data/discovery.db)
  GNN_PORT        HTTP port                      (default: 8501)
"""

from __future__ import annotations

import os
import time
import logging

from flask import Flask, request, jsonify

from data_loader import load_graph, BACKEND
from model import DealerGNNModel, FEAT_DIM, NUM_CLASSES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Global model state ────────────────────────────────────────────────────────

_model: DealerGNNModel | None = None
_embeddings = None       # [N, EMBED_DIM] tensor (precomputed at startup)
_dealer_ids: list[str] = []
_dealer_index: dict[str, int] = {}

# Simple in-process Prometheus-style counters (exported via /metrics)
_requests_total = 0
_latency_sum = 0.0


def _load_model():
    global _model, _embeddings, _dealer_ids, _dealer_index

    import torch

    model_path = os.getenv("GNN_MODEL_PATH", "model.pt")
    db_path = os.getenv("GNN_DB_PATH", "./data/discovery.db")

    if not os.path.exists(model_path):
        log.warning("Model checkpoint not found at %s — serving without embeddings", model_path)
        return

    log.info("Loading model from %s", model_path)
    ckpt = torch.load(model_path, map_location="cpu", weights_only=True)

    cfg = ckpt.get("model_config", {})
    _model = DealerGNNModel(
        in_channels=cfg.get("in_channels", FEAT_DIM),
        hidden_channels=cfg.get("hidden_channels", 64),
        embed_dim=cfg.get("embed_dim", 32),
        num_classes=cfg.get("num_classes", NUM_CLASSES),
        dropout=0.0,  # inference mode — dropout off
    )
    _model.load_state_dict(ckpt["model_state"])
    _model.eval()

    _dealer_ids = ckpt.get("dealer_ids", [])
    _dealer_index = {did: i for i, did in enumerate(_dealer_ids)}

    if not _dealer_ids:
        log.info("No dealer_ids in checkpoint — loading graph from %s", db_path)
        if os.path.exists(db_path):
            data = load_graph(db_path)
            _dealer_ids = getattr(data, "dealer_ids", [])
            _dealer_index = {did: i for i, did in enumerate(_dealer_ids)}

    # Precompute embeddings
    if _dealer_ids:
        import torch
        data = load_graph(db_path) if os.path.exists(db_path) else None
        if data is not None and (BACKEND == "pyg" and data.x.size(0) > 0):
            with torch.no_grad():
                _embeddings = _model.encode(data.x, data.edge_index)
            log.info("Precomputed embeddings for %d dealers", _embeddings.size(0))
        elif data is not None and BACKEND == "dgl":
            with torch.no_grad():
                _embeddings = _model.encode(data, data.ndata["feat"])
            log.info("Precomputed embeddings for %d dealers (DGL)", _embeddings.size(0))

    log.info("Model ready — %d dealers indexed", len(_dealer_ids))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": _model is not None,
        "nodes": len(_dealer_ids),
        "backend": BACKEND,
    })


@app.route("/predict-links", methods=["POST"])
def predict_links():
    global _requests_total, _latency_sum

    t0 = time.perf_counter()
    _requests_total += 1

    body = request.get_json(silent=True) or {}
    dealer_id = body.get("dealer_id", "")
    top_k = int(body.get("top_k", 5))

    if not dealer_id:
        return jsonify({"error": "dealer_id is required"}), 400

    if _model is None or _embeddings is None:
        return jsonify({
            "dealer_id": dealer_id,
            "predicted_links": [],
            "warning": "model not loaded — run make gnn-train first",
        })

    idx = _dealer_index.get(dealer_id)
    if idx is None:
        return jsonify({
            "dealer_id": dealer_id,
            "predicted_links": [],
            "warning": f"dealer_id {dealer_id!r} not in index",
        })

    links = _model.top_k_links(_embeddings, idx, k=top_k)
    result = [
        {
            "dst_dealer_id": _dealer_ids[lnk["dst_idx"]],
            "probability": round(lnk["probability"], 4),
        }
        for lnk in links
        if lnk["dst_idx"] < len(_dealer_ids)
    ]

    elapsed = time.perf_counter() - t0
    _latency_sum += elapsed

    return jsonify({"dealer_id": dealer_id, "predicted_links": result})


@app.route("/classify-node", methods=["POST"])
def classify_node():
    body = request.get_json(silent=True) or {}
    dealer_id = body.get("dealer_id", "")

    if _model is None or _embeddings is None:
        return jsonify({"error": "model not loaded"}), 503

    idx = _dealer_index.get(dealer_id)
    if idx is None:
        return jsonify({"error": f"dealer_id {dealer_id!r} not found"}), 404

    import torch
    with torch.no_grad():
        logits = _model.classify_nodes(_embeddings[idx].unsqueeze(0))
        probs = torch.softmax(logits, dim=-1).squeeze(0)
        predicted = int(probs.argmax())

    from model import CLASS_NAMES
    return jsonify({
        "dealer_id": dealer_id,
        "predicted_class": CLASS_NAMES[predicted],
        "class_probabilities": {
            CLASS_NAMES[i]: round(float(p), 4) for i, p in enumerate(probs.tolist())
        },
    })


@app.route("/metrics", methods=["GET"])
def prometheus_metrics():
    avg_latency = (_latency_sum / _requests_total) if _requests_total > 0 else 0.0
    lines = [
        "# HELP cardex_gnn_requests_total Total predict-links requests",
        "# TYPE cardex_gnn_requests_total counter",
        f"cardex_gnn_requests_total {_requests_total}",
        "# HELP cardex_gnn_latency_seconds_avg Average predict-links latency",
        "# TYPE cardex_gnn_latency_seconds_avg gauge",
        f"cardex_gnn_latency_seconds_avg {avg_latency:.6f}",
        "# HELP cardex_gnn_nodes_indexed Number of dealer nodes in model",
        "# TYPE cardex_gnn_nodes_indexed gauge",
        f"cardex_gnn_nodes_indexed {len(_dealer_ids)}",
    ]
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _load_model()
    port = int(os.getenv("GNN_PORT", "8501"))
    log.info("Starting GNN inference server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
