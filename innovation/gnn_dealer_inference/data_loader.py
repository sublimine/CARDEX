"""
data_loader.py — Load dealer graph from CARDEX SQLite and build PyG/DGL tensors.

Temporal split: edges sorted by first_observed timestamp; most-recent 10% = test,
next 10% = val, remainder = train. Prevents future VIN observations from leaking.
"""

import sqlite3
import os
import numpy as np

BACKEND = "pyg"
try:
    import torch
    import torch_geometric  # noqa: F401
except ImportError:
    BACKEND = "dgl"

# ── Constants ──────────────────────────────────────────────────────────────────

NODE_FEATURE_DIM = 9


def _norm(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise a 1-D array to [0, 1]. Handles zero range."""
    lo, hi = arr.min(), arr.max()
    if hi == lo:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).astype(np.float32)


# ── Graph loader ───────────────────────────────────────────────────────────────

def load_graph(db_path: str, min_shared_vins: int = 1):
    """
    Build a dealer supply graph from CARDEX discovery.db.

    Node features (9-dim):
      0  listing_volume      (log1p, norm)
      1  avg_price           (log1p, norm)
      2  avg_mileage         (log1p, norm)
      3  brand_entropy       (norm)
      4  country_id          (integer 0-N)
      5  dealer_age_days     (log1p, norm)
      6  trust_score         (0-1 float from V15, default 0.5)
      7  cluster_size        (log1p, norm from V21)
      8  is_active           (0 or 1)

    Returns a PyG Data (BACKEND=pyg) or DGL graph (BACKEND=dgl).
    """
    conn = sqlite3.connect(db_path)
    try:
        return _build_graph(conn, min_shared_vins)
    finally:
        conn.close()


def _build_graph(conn: sqlite3.Connection, min_shared_vins: int):
    dealers = _load_dealers(conn)
    if not dealers:
        return _empty_graph()

    dealer_ids = [d["id"] for d in dealers]
    id_to_idx = {did: i for i, did in enumerate(dealer_ids)}

    x = _build_node_features(dealers)
    edges, edge_times = _build_edges(conn, id_to_idx, min_shared_vins)

    if BACKEND == "pyg":
        return _build_pyg(x, edges, edge_times, dealer_ids)
    return _build_dgl(x, edges, edge_times, dealer_ids)


def _load_dealers(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                d.id,
                COUNT(v.id)          AS volume,
                AVG(v.price)         AS avg_price,
                AVG(v.mileage)       AS avg_mileage,
                d.country            AS country,
                JULIANDAY('now') - JULIANDAY(d.created_at) AS age_days,
                COALESCE(d.trust_score, 0.5)   AS trust_score,
                COALESCE(d.cluster_size, 1)    AS cluster_size,
                COALESCE(d.is_active, 1)       AS is_active
            FROM dealer_entity d
            LEFT JOIN vehicle_record v ON v.dealer_id = d.id
            GROUP BY d.id
        """)
    except sqlite3.OperationalError:
        try:
            cur.execute("SELECT id, 'DE' AS country FROM dealer_entity")
        except sqlite3.OperationalError:
            return []
        rows = cur.fetchall()
        return [{"id": r[0], "volume": 0, "avg_price": 0, "avg_mileage": 0,
                 "country": r[1], "age_days": 0, "trust_score": 0.5,
                 "cluster_size": 1, "is_active": 1} for r in rows]

    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _build_node_features(dealers: list[dict]) -> "np.ndarray":
    n = len(dealers)
    volume    = np.array([d.get("volume", 0) or 0       for d in dealers], dtype=np.float32)
    price     = np.array([d.get("avg_price", 0) or 0    for d in dealers], dtype=np.float32)
    mileage   = np.array([d.get("avg_mileage", 0) or 0  for d in dealers], dtype=np.float32)
    age       = np.array([d.get("age_days", 0) or 0     for d in dealers], dtype=np.float32)
    cluster   = np.array([d.get("cluster_size", 1) or 1 for d in dealers], dtype=np.float32)
    trust     = np.array([d.get("trust_score", 0.5) or 0.5 for d in dealers], dtype=np.float32)
    is_active = np.array([float(d.get("is_active", 1) or 1) for d in dealers], dtype=np.float32)

    countries = sorted({d.get("country", "XX") or "XX" for d in dealers})
    c_idx     = {c: i for i, c in enumerate(countries)}
    country   = np.array([c_idx.get(d.get("country", "XX") or "XX", 0)
                          for d in dealers], dtype=np.float32) / max(len(countries) - 1, 1)

    brand_ent = np.full(n, 0.5, dtype=np.float32)

    x = np.stack([
        _norm(np.log1p(volume)),
        _norm(np.log1p(price)),
        _norm(np.log1p(mileage)),
        brand_ent,
        country,
        _norm(np.log1p(age)),
        np.clip(trust, 0.0, 1.0),
        _norm(np.log1p(cluster)),
        is_active,
    ], axis=1)
    assert x.shape == (n, NODE_FEATURE_DIM)
    return x


def _build_edges(conn: sqlite3.Connection, id_to_idx: dict,
                 min_shared_vins: int) -> tuple[list, list]:
    """
    Directed edges: dealer A (earlier) → dealer B (later) for shared VINs.
    Returns (edge_list, edge_times) sorted by first_observed ascending.
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                v1.dealer_id  AS src,
                v2.dealer_id  AS dst,
                MIN(v1.first_observed) AS t
            FROM vehicle_record v1
            JOIN vehicle_record v2
                ON  v1.vin = v2.vin
                AND v1.dealer_id <> v2.dealer_id
                AND v1.first_observed < v2.first_observed
            WHERE v1.dealer_id IS NOT NULL
              AND v2.dealer_id IS NOT NULL
            GROUP BY v1.dealer_id, v2.dealer_id
            HAVING COUNT(*) >= ?
            ORDER BY t ASC
        """, (min_shared_vins,))
    except sqlite3.OperationalError:
        return [], []

    edges, times = [], []
    for src, dst, t in cur.fetchall():
        if src in id_to_idx and dst in id_to_idx:
            edges.append((id_to_idx[src], id_to_idx[dst]))
            times.append(float(t) if t is not None else 0.0)
    return edges, times


def _empty_graph():
    """Return a minimal empty graph for the active backend."""
    if BACKEND == "pyg":
        import torch
        from torch_geometric.data import Data
        return Data(
            x=torch.zeros(0, NODE_FEATURE_DIM),
            edge_index=torch.zeros(2, 0, dtype=torch.long),
            edge_attr=torch.zeros(0, 1),
            dealer_ids=[],
        )
    import dgl
    import torch
    g = dgl.graph(([], []))
    g.ndata["x"] = torch.zeros(0, NODE_FEATURE_DIM)
    g.dealer_ids = []
    return g


def _build_pyg(x, edges, edge_times, dealer_ids):
    import torch
    from torch_geometric.data import Data

    x_t = torch.tensor(x, dtype=torch.float32)
    if edges:
        src, dst = zip(*edges)
        edge_index = torch.tensor([list(src), list(dst)], dtype=torch.long)
        edge_attr  = torch.tensor([[t] for t in edge_times], dtype=torch.float32)
    else:
        edge_index = torch.zeros(2, 0, dtype=torch.long)
        edge_attr  = torch.zeros(0, 1, dtype=torch.float32)

    data = Data(x=x_t, edge_index=edge_index, edge_attr=edge_attr)
    data.dealer_ids = dealer_ids
    return data


def _build_dgl(x, edges, edge_times, dealer_ids):
    import dgl
    import torch

    x_t = torch.tensor(x, dtype=torch.float32)
    if edges:
        src, dst = zip(*edges)
        g = dgl.graph((list(src), list(dst)))
    else:
        g = dgl.graph(([], []))
    g.ndata["x"] = x_t
    if edge_times:
        g.edata["t"] = torch.tensor(edge_times, dtype=torch.float32).unsqueeze(1)
    g.dealer_ids = dealer_ids
    return g


# ── Temporal split ─────────────────────────────────────────────────────────────

def temporal_split(data, val_frac: float = 0.10, test_frac: float = 0.10):
    """
    Split edges by time (anti-leakage). Edges are already sorted ascending
    by first_observed in load_graph.

    Returns (train_mask, val_mask, test_mask) for PyG or DGL.
    """
    if BACKEND == "pyg":
        return _temporal_split_pyg(data, val_frac, test_frac)
    return _temporal_split_dgl(data, val_frac, test_frac)


def _temporal_split_pyg(data, val_frac, test_frac):
    import torch
    n_edges = data.edge_index.size(1)
    if n_edges == 0:
        mask = torch.zeros(0, dtype=torch.bool)
        return mask.clone(), mask.clone(), mask.clone()

    n_test = max(1, int(n_edges * test_frac))
    n_val  = max(1, int(n_edges * val_frac))
    order  = torch.argsort(data.edge_attr[:, 0])

    test_mask  = torch.zeros(n_edges, dtype=torch.bool)
    val_mask   = torch.zeros(n_edges, dtype=torch.bool)
    train_mask = torch.zeros(n_edges, dtype=torch.bool)

    test_mask[order[-n_test:]]                         = True
    val_mask[order[-(n_test + n_val):-n_test]]         = True
    train_mask[order[:-(n_test + n_val)]]              = True

    return train_mask, val_mask, test_mask


def _temporal_split_dgl(data, val_frac, test_frac):
    import torch
    n_edges = data.num_edges()
    if n_edges == 0:
        mask = torch.zeros(0, dtype=torch.bool)
        return mask.clone(), mask.clone(), mask.clone()

    times = data.edata.get("t", torch.zeros(n_edges, 1))[:, 0]
    order = torch.argsort(times)
    n_test = max(1, int(n_edges * test_frac))
    n_val  = max(1, int(n_edges * val_frac))

    test_mask  = torch.zeros(n_edges, dtype=torch.bool)
    val_mask   = torch.zeros(n_edges, dtype=torch.bool)
    train_mask = torch.zeros(n_edges, dtype=torch.bool)

    test_mask[order[-n_test:]]                     = True
    val_mask[order[-(n_test + n_val):-n_test]]     = True
    train_mask[order[:-(n_test + n_val)]]          = True

    return train_mask, val_mask, test_mask
