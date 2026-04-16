"""
test_model.py — Unit tests for GNN model components.

All tests skip gracefully when PyG/DGL is not installed (CI lightweight mode).
"""

import pytest

try:
    import torch
    from model import build_model, EMBED_DIM, NODE_CLASSES, BACKEND
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

pytestmark = pytest.mark.skipif(not HAS_TORCH, reason="torch/PyG/DGL not installed")

N = 20
IN_DIM = 9


@pytest.fixture
def small_pyg_data():
    if BACKEND != "pyg":
        pytest.skip("PyG not available")
    import torch
    from torch_geometric.data import Data
    x = torch.rand(N, IN_DIM)
    src = torch.arange(N)
    dst = torch.roll(src, -1)
    edge_index = torch.stack([src, dst])
    return Data(x=x, edge_index=edge_index)


@pytest.fixture
def small_dgl_data():
    if BACKEND != "dgl":
        pytest.skip("DGL not available")
    import dgl, torch
    src = list(range(N))
    dst = [(i + 1) % N for i in range(N)]
    g = dgl.graph((src, dst))
    g.ndata["x"] = torch.rand(N, IN_DIM)
    return g


def get_z(model, data):
    import torch
    if BACKEND == "pyg":
        with torch.no_grad():
            return model.encode(data.x, data.edge_index)
    else:
        with torch.no_grad():
            return model.encode(data, data.ndata["x"])


def test_encoder_output_shape(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    assert z.shape == (N, EMBED_DIM)


def test_encoder_no_nan(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    import torch
    assert not torch.isnan(z).any()


def test_encoder_eval_deterministic(small_pyg_data, small_dgl_data):
    import torch
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z1 = get_z(model, data)
    z2 = get_z(model, data)
    assert torch.allclose(z1, z2)


def test_link_predictor_range(small_pyg_data, small_dgl_data):
    import torch
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    idx = torch.arange(N // 2)
    probs = model.predict_link(z, idx, idx + N // 2)
    assert probs.min() >= 0.0
    assert probs.max() <= 1.0


def test_node_classifier_shape(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    logits = model.classify_node(z)
    assert logits.shape == (N, len(NODE_CLASSES))


def test_top_k_links_count(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    results = model.top_k_links(z, query_idx=0, k=5)
    assert len(results) == 5


def test_top_k_links_excludes_self(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    results = model.top_k_links(z, query_idx=0, k=5, exclude_self=True)
    assert all(r["dst_idx"] != 0 for r in results)


def test_top_k_links_probability_descending(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    results = model.top_k_links(z, query_idx=0, k=5)
    probs = [r["probability"] for r in results]
    assert probs == sorted(probs, reverse=True)


def test_top_k_links_probability_range(small_pyg_data, small_dgl_data):
    data = small_pyg_data if BACKEND == "pyg" else small_dgl_data
    model = build_model(IN_DIM)
    model.eval()
    z = get_z(model, data)
    results = model.top_k_links(z, query_idx=0, k=3)
    for r in results:
        assert 0.0 <= r["probability"] <= 1.0


def test_training_step_smoke(small_pyg_data, small_dgl_data):
    import torch
    import torch.nn.functional as F
    from torch_geometric.utils import negative_sampling

    if BACKEND != "pyg":
        pytest.skip("training step test is PyG-only")

    data = small_pyg_data
    model = build_model(IN_DIM)
    model.train()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    z = model.encode(data.x, data.edge_index)
    pos = data.edge_index
    neg = negative_sampling(pos, num_nodes=N, num_neg_samples=pos.size(1))
    pos_pred = model.predict_link(z, pos[0], pos[1])
    neg_pred = model.predict_link(z, neg[0], neg[1])
    labels   = torch.cat([torch.ones_like(pos_pred), torch.zeros_like(neg_pred)])
    preds    = torch.cat([pos_pred, neg_pred])
    loss     = F.binary_cross_entropy(preds, labels)

    opt.zero_grad()
    loss.backward()
    opt.step()

    assert torch.isfinite(loss)


def test_build_model_returns_object():
    model = build_model(IN_DIM)
    assert model is not None
