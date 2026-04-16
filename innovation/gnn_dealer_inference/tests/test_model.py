"""
Tests for DealerGNNModel that run without a GPU and without a real SQLite DB.
All tensors are constructed inline so no PyG/DGL data loading is needed.
"""

import pytest
import torch

# Skip entire module if neither PyG nor DGL is installed
try:
    from model import (
        DealerGNNModel,
        DealerGraphSAGE,
        LinkPredictor,
        NodeClassifier,
        FEAT_DIM,
        EMBED_DIM,
        NUM_CLASSES,
        CLASS_NAMES,
        BACKEND,
    )
except ImportError as e:
    pytest.skip(f"GNN backend not installed: {e}", allow_module_level=True)


N = 10   # number of fake dealer nodes
E = 12   # number of fake edges


def _fake_graph():
    """Return (x, edge_index) with N nodes and E random directed edges."""
    torch.manual_seed(0)
    x = torch.rand(N, FEAT_DIM)
    # Cycle + some cross edges so every node has at least one neighbour
    src = torch.arange(E) % N
    dst = (torch.arange(E) + 1) % N
    edge_index = torch.stack([src, dst])
    return x, edge_index


class TestDealerGraphSAGE:
    def test_output_shape(self):
        x, edge_index = _fake_graph()
        encoder = DealerGraphSAGE()
        encoder.eval()
        with torch.no_grad():
            z = encoder(x, edge_index) if BACKEND == "pyg" else None
        if BACKEND == "pyg":
            assert z.shape == (N, EMBED_DIM), f"expected ({N}, {EMBED_DIM}), got {z.shape}"

    def test_no_nan_in_output(self):
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        encoder = DealerGraphSAGE()
        encoder.eval()
        with torch.no_grad():
            z = encoder(x, edge_index)
        assert not torch.isnan(z).any(), "NaN detected in encoder output"

    def test_dropout_off_in_eval(self):
        """Two forward passes in eval mode must give identical output."""
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        encoder = DealerGraphSAGE(dropout=0.9)
        encoder.eval()
        with torch.no_grad():
            z1 = encoder(x, edge_index)
            z2 = encoder(x, edge_index)
        assert torch.allclose(z1, z2), "Eval outputs differ — dropout not disabled"


class TestLinkPredictor:
    def test_output_range(self):
        predictor = LinkPredictor(embed_dim=EMBED_DIM)
        z_src = torch.rand(8, EMBED_DIM)
        z_dst = torch.rand(8, EMBED_DIM)
        probs = predictor(z_src, z_dst)
        assert probs.shape == (8,)
        assert (probs >= 0).all() and (probs <= 1).all(), "probabilities outside [0,1]"

    def test_self_link_symmetry(self):
        """Probability of z→z is not necessarily 0.5, but must be in [0,1]."""
        predictor = LinkPredictor(embed_dim=EMBED_DIM)
        z = torch.rand(1, EMBED_DIM)
        p = predictor(z, z)
        assert 0 <= float(p) <= 1


class TestNodeClassifier:
    def test_output_shape(self):
        clf = NodeClassifier(embed_dim=EMBED_DIM, num_classes=NUM_CLASSES)
        z = torch.rand(N, EMBED_DIM)
        logits = clf(z)
        assert logits.shape == (N, NUM_CLASSES)


class TestDealerGNNModel:
    def test_encode_shape(self):
        if BACKEND != "pyg":
            pytest.skip("PyG required for this test")
        x, edge_index = _fake_graph()
        model = DealerGNNModel()
        model.eval()
        with torch.no_grad():
            z = model.encode(x, edge_index)
        assert z.shape == (N, EMBED_DIM)

    def test_predict_links_shape(self):
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        model = DealerGNNModel()
        model.eval()
        with torch.no_grad():
            z = model.encode(x, edge_index)
            probs = model.predict_links(z, torch.tensor([0, 1, 2]), torch.tensor([3, 4, 5]))
        assert probs.shape == (3,)
        assert (probs >= 0).all() and (probs <= 1).all()

    def test_classify_nodes_shape(self):
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        model = DealerGNNModel()
        model.eval()
        with torch.no_grad():
            z = model.encode(x, edge_index)
            logits = model.classify_nodes(z)
        assert logits.shape == (N, NUM_CLASSES)

    def test_top_k_links_returns_k(self):
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        model = DealerGNNModel()
        model.eval()
        with torch.no_grad():
            z = model.encode(x, edge_index)
        links = model.top_k_links(z, query_idx=0, k=3)
        assert len(links) == 3
        assert all("dst_idx" in l and "probability" in l for l in links)
        assert all(l["dst_idx"] != 0 for l in links), "self-link should be excluded"

    def test_class_names_coverage(self):
        assert set(CLASS_NAMES.values()) == {"WHOLESALE", "RETAIL", "BROKER", "FLEET"}

    def test_training_step_runs(self):
        """Smoke-test: one forward+backward pass does not crash."""
        if BACKEND != "pyg":
            pytest.skip("PyG required")
        x, edge_index = _fake_graph()
        model = DealerGNNModel()
        optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
        optimiser.zero_grad()
        z = model.encode(x, edge_index)
        src = edge_index[0, :4]
        dst = edge_index[1, :4]
        probs = model.predict_links(z, src, dst)
        loss = torch.nn.functional.binary_cross_entropy(probs, torch.ones(4))
        loss.backward()
        optimiser.step()
        assert loss.item() >= 0
