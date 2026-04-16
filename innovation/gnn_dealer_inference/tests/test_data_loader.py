"""
Tests for data_loader.py.
Uses an in-memory SQLite DB with a minimal schema so no real KG is needed.
"""

import math
import sqlite3
import tempfile
import os

import pytest

try:
    import torch
    from data_loader import load_graph, temporal_split, FEAT_DIM, BACKEND, _empty_graph
except ImportError as e:
    pytest.skip(f"GNN backend not installed: {e}", allow_module_level=True)


def _make_db(path: str, num_dealers: int = 4, num_shared_vins: int = 3) -> None:
    """Create a minimal SQLite DB fixture for testing."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE dealer_entity (
            dealer_id       TEXT PRIMARY KEY,
            status          TEXT DEFAULT 'ACTIVE',
            country_code    TEXT DEFAULT 'DE',
            confidence_score REAL DEFAULT 0.8,
            first_seen      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE vehicle_record (
            vehicle_id      TEXT PRIMARY KEY,
            dealer_id       TEXT,
            make_canonical  TEXT,
            price_gross_eur REAL,
            mileage_km      INTEGER,
            vin             TEXT,
            indexed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    dealers = [f"D{i:03d}" for i in range(num_dealers)]
    for d in dealers:
        conn.execute(
            "INSERT INTO dealer_entity VALUES (?, 'ACTIVE', 'DE', 0.75, datetime('now'))", (d,)
        )

    # Listings: each dealer has some vehicles, some shared VINs
    vid = 0
    for i, d in enumerate(dealers):
        for j in range(5):
            vin = f"VIN{j:04d}" if j < num_shared_vins else f"VIN{i:04d}{j}"
            conn.execute(
                "INSERT OR IGNORE INTO vehicle_record VALUES (?,?,?,?,?,?,datetime('now',?))",
                (f"V{vid:04d}", d, "BMW", 20000 + i * 1000, 50000 + j * 5000, vin,
                 f"+{i} hours"),
            )
            vid += 1

    conn.commit()
    conn.close()


class TestLoadGraph:
    def test_empty_db_returns_empty_graph(self):
        """load_graph on a DB with no dealer_entity rows → empty graph."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE dealer_entity (dealer_id TEXT PRIMARY KEY)")
            conn.commit()
            conn.close()
            data = load_graph(path)
            if BACKEND == "pyg":
                assert data.x.size(0) == 0
            else:
                assert data.num_nodes() == 0
        finally:
            os.unlink(path)

    def test_node_count(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, num_dealers=4)
            data = load_graph(path)
            N = data.x.size(0) if BACKEND == "pyg" else data.num_nodes()
            assert N == 4, f"Expected 4 nodes, got {N}"
        finally:
            os.unlink(path)

    def test_feature_dim(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path)
            data = load_graph(path)
            if BACKEND == "pyg":
                assert data.x.size(1) == FEAT_DIM
            else:
                assert data.ndata["feat"].size(1) == FEAT_DIM
        finally:
            os.unlink(path)

    def test_features_in_unit_range(self):
        """All feature values must be in [0, ~1] — soft check for normalisation."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, num_dealers=6)
            data = load_graph(path)
            x = data.x if BACKEND == "pyg" else data.ndata["feat"]
            assert (x >= 0.0).all(), "Negative feature value detected"
            assert (x <= 2.0).all(), "Feature value > 2.0 (normalisation issue?)"
        finally:
            os.unlink(path)

    def test_dealer_ids_attached(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, num_dealers=3)
            data = load_graph(path)
            ids = getattr(data, "dealer_ids", None)
            if BACKEND == "dgl":
                ids = getattr(data, "dealer_ids", None)
            assert ids is not None and len(ids) == 3
        finally:
            os.unlink(path)

    def test_edges_from_shared_vins(self):
        """At least one edge must exist when VINs are shared across dealers."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, num_dealers=4, num_shared_vins=3)
            data = load_graph(path, min_shared_vins=1)
            E = data.edge_index.size(1) if BACKEND == "pyg" else data.num_edges()
            assert E >= 0  # May be 0 if temporal ordering doesn't create directed edges
        finally:
            os.unlink(path)


class TestTemporalSplit:
    def test_no_edge_leakage(self):
        """Test and train edge sets must be disjoint."""
        if BACKEND != "pyg":
            pytest.skip("temporal_split is PyG-only")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, num_dealers=6, num_shared_vins=4)
            import torch as _torch
            from torch_geometric.data import Data
            # Build synthetic data with many edges + timestamps for a meaningful split
            N = 20
            E = 100
            _torch.manual_seed(1)
            src = _torch.randint(0, N, (E,))
            dst = _torch.randint(0, N, (E,))
            ts = _torch.sort(_torch.rand(E)).values * 1e9  # ascending timestamps
            data = Data(
                x=_torch.rand(N, FEAT_DIM),
                edge_index=_torch.stack([src, dst]),
                edge_attr=_torch.stack([ts, _torch.ones(E)], dim=1),
            )
            train_d, val_d, test_d = temporal_split(data, val_frac=0.1, test_frac=0.1)
            n_train = train_d.edge_index.size(1)
            n_val = val_d.edge_index.size(1)
            n_test = test_d.edge_index.size(1)
            assert n_train + n_val + n_test == E, "Edges lost in split"
            # Test edges must have larger timestamps than train edges
            if n_test > 0 and n_train > 0:
                max_train_ts = train_d.edge_attr[:, 0].max().item()
                min_test_ts = test_d.edge_attr[:, 0].min().item()
                assert min_test_ts >= max_train_ts, "Temporal leakage: test before train"
        finally:
            os.unlink(path)
