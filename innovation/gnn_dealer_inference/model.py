"""
model.py — GraphSAGE 2-layer encoder + task heads for dealer graph inference.

Architecture
------------
GraphSAGE encoder (2 layers):
  Layer 1: SAGEConv(FEAT_DIM=9, hidden_dim=64), ReLU, Dropout(0.3)
  Layer 2: SAGEConv(64, embed_dim=32)

Task heads:
  Link predictor:  MLP over [z_u || z_v || z_u * z_v] → sigmoid probability
  Node classifier: Linear(embed_dim, num_classes=4) → softmax
                   Classes: 0=WHOLESALE, 1=RETAIL, 2=BROKER, 3=FLEET

All operations are CPU-compatible — no CUDA requirement.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from torch_geometric.nn import SAGEConv
    BACKEND = "pyg"
except ImportError:
    try:
        import dgl
        import dgl.nn as dglnn
        BACKEND = "dgl"
    except ImportError:
        raise ImportError(
            "PyTorch Geometric or DGL is required. See data_loader.py for install instructions."
        )

FEAT_DIM = 9
HIDDEN_DIM = 64
EMBED_DIM = 32
NUM_CLASSES = 4  # WHOLESALE, RETAIL, BROKER, FLEET

# Maps integer class index to human-readable label
CLASS_NAMES = {0: "WHOLESALE", 1: "RETAIL", 2: "BROKER", 3: "FLEET"}


class DealerGraphSAGE(nn.Module):
    """
    2-layer GraphSAGE encoder producing a 32-dim embedding per dealer node.

    Compatible with both PyTorch Geometric and DGL backends.
    """

    def __init__(
        self,
        in_channels: int = FEAT_DIM,
        hidden_channels: int = HIDDEN_DIM,
        out_channels: int = EMBED_DIM,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.dropout = dropout
        if BACKEND == "pyg":
            self.conv1 = SAGEConv(in_channels, hidden_channels, aggr="mean")
            self.conv2 = SAGEConv(hidden_channels, out_channels, aggr="mean")
        else:
            self.conv1 = dglnn.SAGEConv(in_channels, hidden_channels, aggregator_type="mean")
            self.conv2 = dglnn.SAGEConv(hidden_channels, out_channels, aggregator_type="mean")

    def forward(self, x_or_g, edge_index_or_none=None):
        """
        PyG call: forward(x, edge_index) → z  [N, EMBED_DIM]
        DGL call: forward(g, g.ndata['feat']) → z  [N, EMBED_DIM]
        """
        if BACKEND == "pyg":
            x, edge_index = x_or_g, edge_index_or_none
            x = self.conv1(x, edge_index)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
            x = self.conv2(x, edge_index)
            return x
        else:
            g, feat = x_or_g, edge_index_or_none
            h = self.conv1(g, feat)
            h = F.relu(h)
            h = F.dropout(h, p=self.dropout, training=self.training)
            h = self.conv2(g, h)
            return h


class LinkPredictor(nn.Module):
    """
    Predicts the probability of a directed edge A→B (dealer A supplies stock to B).

    Input: concatenation of [z_A || z_B || z_A * z_B]  (3 × EMBED_DIM = 96 features)
    Output: scalar probability in [0, 1]
    """

    def __init__(self, embed_dim: int = EMBED_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(3 * embed_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1),
        )

    def forward(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        h = torch.cat([z_src, z_dst, z_src * z_dst], dim=-1)
        return torch.sigmoid(self.net(h)).squeeze(-1)


class NodeClassifier(nn.Module):
    """
    Classifies each dealer node into one of 4 categories.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.fc = nn.Linear(embed_dim, num_classes)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.fc(z)  # raw logits — apply softmax externally if needed


class DealerGNNModel(nn.Module):
    """
    Full model combining the GraphSAGE encoder with both task heads.

    Usage (PyG):
        model = DealerGNNModel()
        z = model.encode(x, edge_index)
        link_prob = model.predict_links(z, src_idx, dst_idx)
        class_logits = model.classify_nodes(z)

    Usage (DGL):
        z = model.encode(g, g.ndata['feat'])
        ...
    """

    def __init__(
        self,
        in_channels: int = FEAT_DIM,
        hidden_channels: int = HIDDEN_DIM,
        embed_dim: int = EMBED_DIM,
        num_classes: int = NUM_CLASSES,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.encoder = DealerGraphSAGE(in_channels, hidden_channels, embed_dim, dropout)
        self.link_predictor = LinkPredictor(embed_dim)
        self.node_classifier = NodeClassifier(embed_dim, num_classes)

    def encode(self, x_or_g, edge_index_or_feat=None) -> torch.Tensor:
        return self.encoder(x_or_g, edge_index_or_feat)

    def predict_links(
        self,
        z: torch.Tensor,
        src_idx: torch.Tensor,
        dst_idx: torch.Tensor,
    ) -> torch.Tensor:
        return self.link_predictor(z[src_idx], z[dst_idx])

    def classify_nodes(self, z: torch.Tensor) -> torch.Tensor:
        return self.node_classifier(z)

    @torch.no_grad()
    def top_k_links(
        self,
        z: torch.Tensor,
        query_idx: int,
        k: int = 5,
        exclude_self: bool = True,
    ) -> list[dict]:
        """
        For a given dealer node, return the top-K most probable link targets.

        Returns a list of dicts: [{dst_idx, probability}, ...]
        """
        N = z.size(0)
        src = z[query_idx].unsqueeze(0).expand(N, -1)
        dst = z
        probs = self.link_predictor(src, dst)
        if exclude_self:
            probs[query_idx] = 0.0
        topk_probs, topk_idx = torch.topk(probs, min(k, N - 1))
        return [
            {"dst_idx": int(i), "probability": float(p)}
            for i, p in zip(topk_idx.tolist(), topk_probs.tolist())
        ]
