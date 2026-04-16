"""
data_loader.py — build a PyTorch Geometric HeteroData graph from the CARDEX SQLite KG.

Graph topology
--------------
Nodes  : dealers (dealer_entity table)
Edges  : inferred from shared-VIN observations, geographic proximity, and
         same enterprise group.  Two dealers are connected if the same VIN
         appears at both (temporal ordering determines edge direction: seller → buyer).

Node features (float32, 9-dim)
-------------------------------
  0  listing_volume          normalised count of vehicle listings
  1  avg_price_eur           mean price, log-scaled
  2  avg_mileage_km          mean odometer, log-scaled
  3  brand_entropy           Shannon entropy over make distribution
  4  country_code_int        one-hot collapsed to ordinal (DE=0,FR=1,ES=2,NL=3,BE=4,CH=5,OTHER=6)
  5  dealer_age_days         days since first_seen, log-scaled
  6  v15_trust_score         normalised dealer trust score [0,1]
  7  v21_entity_cluster_size normalised V21 canonical cluster size
  8  is_active               1.0 if status='ACTIVE' else 0.0

Edge labels (for temporal split)
---------------------------------
  edge_attr[0] = first_observed timestamp (Unix epoch, not used as feature — only for splitting)
  edge_attr[1] = vin_count (number of shared VINs supporting this edge)
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Optional

import numpy as np

# PyTorch Geometric import with fallback guidance
try:
    import torch
    from torch_geometric.data import Data, HeteroData
    BACKEND = "pyg"
except ImportError:
    try:
        import dgl
        import torch
        BACKEND = "dgl"
    except ImportError:
        raise ImportError(
            "Neither PyTorch Geometric nor DGL is installed.\n"
            "CPU-only install:\n"
            "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install torch_geometric\n"
            "  pip install pyg_lib torch_scatter torch_sparse -f "
            "https://data.pyg.org/whl/torch-2.5.0+cpu.html\n"
            "DGL alternative:\n"
            "  pip install dgl -f https://data.dgl.ai/wheels/torch-2.5/repo.html"
        )

COUNTRY_MAP = {"DE": 0, "FR": 1, "ES": 2, "NL": 3, "BE": 4, "CH": 5}
FEAT_DIM = 9


def _safe_log(x: float) -> float:
    return math.log1p(max(x, 0.0))


def load_graph(db_path: str, min_shared_vins: int = 1) -> "Data | dgl.DGLGraph":
    """
    Load the dealer graph from the SQLite KG at *db_path*.

    Returns a PyG ``Data`` object (or DGL ``DGLGraph`` when PyG is absent) with:
      - x          : float32 node feature matrix  [N, FEAT_DIM]
      - edge_index : long tensor                   [2, E]  (src→dst)
      - edge_attr  : float32 edge features         [E, 2]
      - dealer_ids : list[str]                     dealer_id for node i
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Dealers (nodes) ──────────────────────────────────────────────────────
    cur.execute("""
        SELECT
            d.dealer_id,
            d.status,
            COALESCE(d.country_code, 'OTHER')                          AS country,
            COALESCE(d.confidence_score, 0.0)                          AS trust_score,
            COALESCE(JULIANDAY('now') - JULIANDAY(d.first_seen), 0)    AS age_days,
            COUNT(v.vehicle_id)                                         AS listing_volume,
            AVG(COALESCE(v.price_gross_eur, 0))                        AS avg_price,
            AVG(COALESCE(v.mileage_km, 0))                             AS avg_mileage
        FROM dealer_entity d
        LEFT JOIN vehicle_record v ON v.dealer_id = d.dealer_id
        GROUP BY d.dealer_id
        ORDER BY d.dealer_id
    """)
    dealer_rows = cur.fetchall()

    if not dealer_rows:
        conn.close()
        return _empty_graph()

    dealer_index: dict[str, int] = {r["dealer_id"]: i for i, r in enumerate(dealer_rows)}
    N = len(dealer_rows)

    # ── Brand entropy per dealer ─────────────────────────────────────────────
    cur.execute("""
        SELECT dealer_id, make_canonical, COUNT(*) AS cnt
        FROM vehicle_record
        WHERE dealer_id IS NOT NULL AND make_canonical IS NOT NULL
        GROUP BY dealer_id, make_canonical
    """)
    make_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in cur.fetchall():
        make_counts[row["dealer_id"]][row["make_canonical"]] = row["cnt"]

    # ── V21 entity cluster sizes ─────────────────────────────────────────────
    entity_cluster: dict[str, int] = {}
    try:
        cur.execute("""
            SELECT text, COUNT(*) AS sz
            FROM entity_embeddings
            GROUP BY text
        """)
        for row in cur.fetchall():
            entity_cluster[row["text"]] = row["sz"]
    except sqlite3.OperationalError:
        pass  # entity_embeddings table not yet populated

    # ── Build feature matrix ─────────────────────────────────────────────────
    # Normalisation constants (approximate domain ranges)
    max_volume = max(r["listing_volume"] for r in dealer_rows) or 1.0
    max_age = max(r["age_days"] for r in dealer_rows) or 1.0
    max_cluster = max(entity_cluster.values(), default=1)

    feats = np.zeros((N, FEAT_DIM), dtype=np.float32)
    for i, r in enumerate(dealer_rows):
        did = r["dealer_id"]
        counts = make_counts.get(did, {})
        total = sum(counts.values()) or 1
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values() if c > 0)

        feats[i, 0] = r["listing_volume"] / max_volume
        feats[i, 1] = _safe_log(r["avg_price"]) / 15.0      # ln(3_000_000) ≈ 15
        feats[i, 2] = _safe_log(r["avg_mileage"]) / 12.0    # ln(300_000) ≈ 12.6
        feats[i, 3] = entropy / math.log2(max(len(counts), 2))
        feats[i, 4] = COUNTRY_MAP.get(r["country"], 6) / 6.0
        feats[i, 5] = _safe_log(r["age_days"]) / _safe_log(max_age)
        feats[i, 6] = float(r["trust_score"])
        feats[i, 7] = entity_cluster.get(did, 1) / max_cluster
        feats[i, 8] = 1.0 if r["status"] == "ACTIVE" else 0.0

    # ── Edges: shared VINs ───────────────────────────────────────────────────
    # VIN appears at dealer A (earlier) → dealer B (later): edge A→B
    try:
        cur.execute("""
            SELECT
                a.dealer_id         AS src,
                b.dealer_id         AS dst,
                COUNT(*)            AS vin_cnt,
                MIN(b.indexed_at)   AS first_obs
            FROM vehicle_record a
            JOIN vehicle_record b ON b.vin = a.vin
                                 AND b.dealer_id != a.dealer_id
                                 AND b.indexed_at > a.indexed_at
            WHERE a.vin IS NOT NULL
              AND a.dealer_id IS NOT NULL
              AND b.dealer_id IS NOT NULL
            GROUP BY a.dealer_id, b.dealer_id
            HAVING COUNT(*) >= ?
            ORDER BY first_obs
        """, (min_shared_vins,))
        edge_rows = cur.fetchall()
    except sqlite3.OperationalError:
        edge_rows = []

    conn.close()

    src_list, dst_list = [], []
    edge_attr_list = []
    for row in edge_rows:
        s = dealer_index.get(row["src"])
        d = dealer_index.get(row["dst"])
        if s is None or d is None:
            continue
        src_list.append(s)
        dst_list.append(d)
        try:
            import time
            import datetime
            dt = datetime.datetime.fromisoformat(row["first_obs"]) if row["first_obs"] else datetime.datetime.utcnow()
            ts = dt.timestamp()
        except Exception:
            ts = 0.0
        edge_attr_list.append([ts, float(row["vin_cnt"])])

    dealer_ids = [r["dealer_id"] for r in dealer_rows]

    if BACKEND == "pyg":
        x = torch.tensor(feats, dtype=torch.float32)
        if src_list:
            edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
            edge_attr = torch.tensor(edge_attr_list, dtype=torch.float32)
        else:
            edge_index = torch.zeros((2, 0), dtype=torch.long)
            edge_attr = torch.zeros((0, 2), dtype=torch.float32)
        data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
        data.dealer_ids = dealer_ids
        return data
    else:
        # DGL path
        if src_list:
            g = dgl.graph((src_list, dst_list), num_nodes=N)
        else:
            g = dgl.graph(([], []), num_nodes=N)
        g.ndata["feat"] = torch.tensor(feats, dtype=torch.float32)
        if edge_attr_list:
            g.edata["attr"] = torch.tensor(edge_attr_list, dtype=torch.float32)
        g.dealer_ids = dealer_ids
        return g


def temporal_split(
    data: "Data",
    val_frac: float = 0.1,
    test_frac: float = 0.1,
) -> tuple["Data", "Data", "Data"]:
    """
    Split edges temporally (train / val / test) to avoid data leakage.

    Edges are sorted by first_observed timestamp (edge_attr[:, 0]).
    The most recent *test_frac* of edges form the test set,
    the next *val_frac* form the validation set,
    and the remainder form the training set.
    """
    if BACKEND != "pyg":
        raise NotImplementedError("temporal_split only supported with PyTorch Geometric backend")

    E = data.edge_index.size(1)
    if E == 0:
        return data, data, data

    order = data.edge_attr[:, 0].argsort()
    n_test = max(1, int(E * test_frac))
    n_val = max(1, int(E * val_frac))

    test_idx = order[-n_test:]
    val_idx = order[-(n_test + n_val): -n_test]
    train_idx = order[: -(n_test + n_val)]

    def _subset(idx):
        d = data.clone()
        d.edge_index = data.edge_index[:, idx]
        d.edge_attr = data.edge_attr[idx]
        return d

    return _subset(train_idx), _subset(val_idx), _subset(test_idx)


def _empty_graph() -> "Data":
    if BACKEND == "pyg":
        return Data(
            x=torch.zeros((0, FEAT_DIM), dtype=torch.float32),
            edge_index=torch.zeros((2, 0), dtype=torch.long),
            edge_attr=torch.zeros((0, 2), dtype=torch.float32),
        )
    else:
        return dgl.graph(([], []))
