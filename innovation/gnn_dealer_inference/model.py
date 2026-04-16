"""
model.py — GraphSAGE 2-layer encoder + link predictor + node classifier.

Architecture:
  Input [N, 9]
    → SAGEConv(9→64, aggr=mean) + ReLU + Dropout(0.3)
    → SAGEConv(64→32, aggr=mean)
    → Embeddings Z [N, 32]
  Link head:  MLP([z_u || z_v || z_u*z_v]) → sigmoid probability
  Node head:  Linear(32, 4) → {WHOLESALE, RETAIL, BROKER, FLEET}
"""

BACKEND = "pyg"
try:
    import torch
    import torch_geometric  # noqa: F401
except ImportError:
    BACKEND = "dgl"

NODE_CLASSES = ["WHOLESALE", "RETAIL", "BROKER", "FLEET"]
EMBED_DIM = 32


def _build_pyg_model(in_channels: int, hidden: int, embed_dim: int, dropout: float):
    import torch
    import torch.nn as nn
    from torch_geometric.nn import SAGEConv

    class DealerGraphSAGE(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = SAGEConv(in_channels, hidden, aggr="mean")
            self.conv2 = SAGEConv(hidden, embed_dim, aggr="mean")
            self.drop  = nn.Dropout(dropout)

        def forward(self, x, edge_index):
            import torch.nn.functional as F
            x = F.relu(self.conv1(x, edge_index))
            x = self.drop(x)
            return self.conv2(x, edge_index)

    class LinkPredictor(nn.Module):
        def __init__(self):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(embed_dim * 3, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

        def forward(self, z_u, z_v):
            return torch.sigmoid(self.mlp(torch.cat([z_u, z_v, z_u * z_v], dim=-1)))

    class NodeClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(embed_dim, len(NODE_CLASSES))

        def forward(self, z):
            return self.fc(z)

    class DealerGNNModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder    = DealerGraphSAGE()
            self.link_head  = LinkPredictor()
            self.node_head  = NodeClassifier()

        def encode(self, x, edge_index):
            return self.encoder(x, edge_index)

        def predict_link(self, z, src, dst):
            return self.link_head(z[src], z[dst])

        def classify_node(self, z):
            return self.node_head(z)

        @torch.no_grad()
        def top_k_links(self, z, query_idx: int, k: int = 5,
                        exclude_self: bool = True) -> list[dict]:
            n = z.size(0)
            q = z[query_idx].unsqueeze(0).expand(n, -1)
            probs = self.link_head(q, z).squeeze(1)
            if exclude_self:
                probs[query_idx] = -1.0
            top_k = min(k, n - (1 if exclude_self else 0))
            vals, idxs = torch.topk(probs, top_k)
            return [{"dst_idx": int(idxs[i]), "probability": float(vals[i])}
                    for i in range(top_k)]

    return DealerGNNModel()


def _build_dgl_model(in_channels: int, hidden: int, embed_dim: int, dropout: float):
    import torch
    import torch.nn as nn

    try:
        from dgl.nn import SAGEConv
    except ImportError:
        raise ImportError("Neither PyTorch Geometric nor DGL is installed")

    class DGLEncoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = SAGEConv(in_channels, hidden, aggregator_type="mean")
            self.conv2 = SAGEConv(hidden, embed_dim, aggregator_type="mean")
            self.drop  = nn.Dropout(dropout)

        def forward(self, g, x):
            import torch.nn.functional as F
            x = F.relu(self.conv1(g, x))
            x = self.drop(x)
            return self.conv2(g, x)

    class DGLLinkPredictor(nn.Module):
        def __init__(self):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(embed_dim * 3, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

        def forward(self, z_u, z_v):
            return torch.sigmoid(self.mlp(torch.cat([z_u, z_v, z_u * z_v], dim=-1)))

    class DGLGNNModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder   = DGLEncoder()
            self.link_head = DGLLinkPredictor()
            self.node_head = nn.Linear(embed_dim, len(NODE_CLASSES))

        def encode(self, g, x):
            return self.encoder(g, x)

        def predict_link(self, z, src, dst):
            return self.link_head(z[src], z[dst])

        def classify_node(self, z):
            return self.node_head(z)

        @torch.no_grad()
        def top_k_links(self, z, query_idx: int, k: int = 5,
                        exclude_self: bool = True) -> list[dict]:
            n = z.size(0)
            q = z[query_idx].unsqueeze(0).expand(n, -1)
            probs = self.link_head(q, z).squeeze(1)
            if exclude_self:
                probs[query_idx] = -1.0
            top_k = min(k, n - (1 if exclude_self else 0))
            vals, idxs = torch.topk(probs, top_k)
            return [{"dst_idx": int(idxs[i]), "probability": float(vals[i])}
                    for i in range(top_k)]

    return DGLGNNModel()


def build_model(in_channels: int = 9, hidden: int = 64,
                embed_dim: int = EMBED_DIM, dropout: float = 0.3):
    """Return a DealerGNNModel using PyG or DGL backend."""
    if BACKEND == "pyg":
        return _build_pyg_model(in_channels, hidden, embed_dim, dropout)
    return _build_dgl_model(in_channels, hidden, embed_dim, dropout)
