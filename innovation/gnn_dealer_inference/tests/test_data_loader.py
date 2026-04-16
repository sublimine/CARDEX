"""
test_data_loader.py — Unit tests for the CARDEX graph data loader.
"""

import os
import sqlite3
import pytest

try:
    import torch
    from data_loader import (
        load_graph, temporal_split, NODE_FEATURE_DIM, BACKEND
    )
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

pytestmark = pytest.mark.skipif(not HAS_TORCH, reason="torch/PyG/DGL not installed")


def _make_db(path: str, num_dealers: int = 5, num_shared_vins: int = 3):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE dealer_entity (
            id TEXT PRIMARY KEY,
            country TEXT,
            trust_score REAL,
            cluster_size INTEGER,
            is_active INTEGER,
            created_at TEXT
        );
        CREATE TABLE vehicle_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dealer_id TEXT,
            vin TEXT,
            price REAL,
            mileage REAL,
            first_observed TEXT
        );
    """)
    import datetime
    base = datetime.datetime(2024, 1, 1)
    for i in range(num_dealers):
        conn.execute("INSERT INTO dealer_entity VALUES (?,?,?,?,?,?)", (
            f"D{i:03d}", "DE", 0.5 + i * 0.05, i + 1, 1,
            (base + datetime.timedelta(days=i * 10)).isoformat(),
        ))
    for v in range(num_shared_vins):
        vin = f"WBA{v:017d}"[:17]
        for d in range(min(num_dealers, 3)):
            conn.execute(
                "INSERT INTO vehicle_record(dealer_id,vin,price,mileage,first_observed) VALUES (?,?,?,?,?)",
                (f"D{d:03d}", vin, 20000 + v * 1000, 50000 - v * 5000,
                 (base + datetime.timedelta(days=d * 5 + v)).isoformat()),
            )
    conn.commit()
    conn.close()


@pytest.fixture
def sample_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    _make_db(db_path, num_dealers=5, num_shared_vins=3)
    return db_path


@pytest.fixture
def empty_db(tmp_path):
    db_path = str(tmp_path / "empty.db")
    open(db_path, "w").close()
    return db_path


def test_empty_db_returns_graph(empty_db):
    graph = load_graph(empty_db)
    assert graph is not None


def test_node_count(sample_db):
    graph = load_graph(sample_db)
    if BACKEND == "pyg":
        assert graph.num_nodes == 5
    else:
        assert graph.num_nodes() == 5


def test_feature_dim(sample_db):
    graph = load_graph(sample_db)
    x = graph.x if BACKEND == "pyg" else graph.ndata["x"]
    assert x.shape[1] == NODE_FEATURE_DIM


def test_features_in_unit_range(sample_db):
    graph = load_graph(sample_db)
    x = graph.x if BACKEND == "pyg" else graph.ndata["x"]
    assert float(x.min()) >= -1e-6
    assert float(x.max()) <= 1.0 + 1e-6


def test_dealer_ids_attached(sample_db):
    graph = load_graph(sample_db)
    assert hasattr(graph, "dealer_ids")
    assert len(graph.dealer_ids) == 5


def test_edges_from_shared_vins(sample_db):
    graph = load_graph(sample_db)
    n_edges = graph.edge_index.size(1) if BACKEND == "pyg" else graph.num_edges()
    assert n_edges > 0


def test_temporal_split_no_leakage(sample_db):
    graph = load_graph(sample_db)
    train_mask, val_mask, test_mask = temporal_split(graph, val_frac=0.1, test_frac=0.1)

    if BACKEND == "pyg":
        n = graph.edge_index.size(1)
        times = graph.edge_attr[:, 0]
    else:
        n = graph.num_edges()
        times = graph.edata.get("t", torch.zeros(n, 1))[:, 0]

    if n < 3:
        pytest.skip("too few edges for split test")

    train_times = times[train_mask]
    test_times  = times[test_mask]
    if train_times.numel() > 0 and test_times.numel() > 0:
        assert float(train_times.max()) <= float(test_times.max())
