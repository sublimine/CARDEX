"""
serve.py — Flask inference server for the GNN dealer link predictor.

Endpoints:
  POST /predict-links  {"dealer_id": "D123", "top_k": 5}
  GET  /health
  GET  /metrics        Prometheus text format

Env:
  GNN_MODEL_PATH   path to model.pt checkpoint  (required)
  GNN_DB_PATH      path to discovery.db          (required for re-encoding)
  GNN_PORT         port to listen on             (default: 8501)
"""

import os
import time
import threading

from flask import Flask, jsonify, request

app = Flask(__name__)

_model      = None
_z          = None
_dealer_ids: list[str] = []
_id_to_idx: dict[str, int] = {}
_backend    = "pyg"
_lock       = threading.Lock()

_prom_requests   = 0
_prom_errors     = 0
_prom_latency_ms: list[float] = []


def _load_model():
    global _model, _z, _dealer_ids, _id_to_idx, _backend

    import torch
    from model import build_model
    from data_loader import load_graph, BACKEND

    model_path = os.environ.get("GNN_MODEL_PATH", "model.pt")
    db_path    = os.environ.get("GNN_DB_PATH", "")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"GNN model not found: {model_path}")

    ckpt    = torch.load(model_path, map_location="cpu", weights_only=True)
    cfg     = ckpt["model_config"]
    _backend = ckpt.get("backend", BACKEND)

    m = build_model(**cfg)
    m.load_state_dict(ckpt["model_state"])
    m.eval()

    ids = ckpt.get("dealer_ids", [])

    if db_path and os.path.exists(db_path):
        data = load_graph(db_path)
        if _backend == "pyg":
            with torch.no_grad():
                z = m.encode(data.x, data.edge_index)
        else:
            with torch.no_grad():
                z = m.encode(data, data.ndata["x"])
        ids = data.dealer_ids
    else:
        z = torch.zeros(len(ids), cfg["embed_dim"])

    with _lock:
        _model      = m
        _z          = z
        _dealer_ids = ids
        _id_to_idx  = {d: i for i, d in enumerate(ids)}


@app.route("/predict-links", methods=["POST"])
def predict_links():
    global _prom_requests, _prom_errors, _prom_latency_ms

    _prom_requests += 1
    t0 = time.monotonic()

    body      = request.get_json(force=True, silent=True) or {}
    dealer_id = body.get("dealer_id", "")
    top_k     = int(body.get("top_k", 5))

    if _model is None:
        _prom_errors += 1
        return jsonify({"error": "model not loaded"}), 503

    idx = _id_to_idx.get(dealer_id)
    if idx is None:
        elapsed = (time.monotonic() - t0) * 1000
        _prom_latency_ms.append(elapsed)
        return jsonify({
            "dealer_id":       dealer_id,
            "predicted_links": [],
            "warning":         "dealer not in index",
        })

    try:
        with _lock:
            results = _model.top_k_links(_z, idx, k=top_k)
        links = [
            {"dst_dealer_id": _dealer_ids[r["dst_idx"]], "probability": r["probability"]}
            for r in results
            if r["dst_idx"] < len(_dealer_ids)
        ]
    except Exception as exc:
        _prom_errors += 1
        return jsonify({"error": str(exc)}), 500

    elapsed = (time.monotonic() - t0) * 1000
    _prom_latency_ms.append(elapsed)
    return jsonify({"dealer_id": dealer_id, "predicted_links": links})


@app.route("/health")
def health():
    return jsonify({
        "status":  "ok" if _model is not None else "loading",
        "nodes":   len(_dealer_ids),
        "backend": _backend,
    })


@app.route("/metrics")
def metrics():
    p50 = p99 = 0.0
    if _prom_latency_ms:
        import statistics
        sorted_ms = sorted(_prom_latency_ms)
        p50 = sorted_ms[int(len(sorted_ms) * 0.50)]
        p99 = sorted_ms[min(int(len(sorted_ms) * 0.99), len(sorted_ms) - 1)]

    lines = [
        "# HELP cardex_gnn_requests_total Total /predict-links calls",
        "# TYPE cardex_gnn_requests_total counter",
        f"cardex_gnn_requests_total {_prom_requests}",
        "# HELP cardex_gnn_errors_total Total /predict-links errors",
        "# TYPE cardex_gnn_errors_total counter",
        f"cardex_gnn_errors_total {_prom_errors}",
        "# HELP cardex_gnn_latency_p50_ms p50 latency ms",
        "# TYPE cardex_gnn_latency_p50_ms gauge",
        f"cardex_gnn_latency_p50_ms {p50:.2f}",
        "# HELP cardex_gnn_latency_p99_ms p99 latency ms",
        "# TYPE cardex_gnn_latency_p99_ms gauge",
        f"cardex_gnn_latency_p99_ms {p99:.2f}",
        "# HELP cardex_gnn_dealer_count Number of dealers in index",
        "# TYPE cardex_gnn_dealer_count gauge",
        f"cardex_gnn_dealer_count {len(_dealer_ids)}",
    ]
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"}


if __name__ == "__main__":
    try:
        _load_model()
        print(f"[GNN] Model loaded — {len(_dealer_ids)} dealers, backend={_backend}")
    except FileNotFoundError as exc:
        print(f"[GNN] WARNING: {exc} — serving /health only until model is available")

    port = int(os.environ.get("GNN_PORT", 8501))
    app.run(host="0.0.0.0", port=port, threaded=True)
