"""
train.py — Train GraphSAGE on CARDEX dealer supply graph.

Usage:
  python train.py --db ../../data/discovery.db --output model.pt \\
                  --epochs 100 --lr 0.005

Checkpoint: model.pt
  {
    "model_state": state_dict,
    "model_config": {in_channels, hidden, embed_dim, dropout},
    "dealer_ids": [str, ...],
    "backend": "pyg" | "dgl",
    "val_auc": float,
    "test_auc": float,
  }
"""

import argparse
import sys

import torch
import torch.nn.functional as F

from data_loader import load_graph, temporal_split, BACKEND, NODE_FEATURE_DIM
from model import build_model


def _negative_sample_pyg(num_nodes: int, pos_edge_index, n_neg: int):
    from torch_geometric.utils import negative_sampling
    return negative_sampling(
        edge_index=pos_edge_index,
        num_nodes=num_nodes,
        num_neg_samples=n_neg,
    )


def _auc_pyg(model, z, pos_edge_index, neg_edge_index) -> float:
    from sklearn.metrics import roc_auc_score
    with torch.no_grad():
        pos_pred = model.predict_link(z, pos_edge_index[0], pos_edge_index[1]).squeeze()
        neg_pred = model.predict_link(z, neg_edge_index[0], neg_edge_index[1]).squeeze()
    y_true  = torch.cat([torch.ones(pos_pred.size(0)), torch.zeros(neg_pred.size(0))])
    y_score = torch.cat([pos_pred, neg_pred]).cpu().numpy()
    if y_true.sum() == 0 or y_true.sum() == len(y_true):
        return 0.5
    return float(roc_auc_score(y_true.numpy(), y_score))


def train(
    db_path: str,
    output_path: str,
    epochs: int = 100,
    lr: float = 5e-3,
    hidden: int = 64,
    embed_dim: int = 32,
    dropout: float = 0.3,
    val_frac: float = 0.10,
    test_frac: float = 0.10,
    verbose: bool = True,
) -> dict:
    data = load_graph(db_path)

    if BACKEND == "pyg":
        return _train_pyg(data, output_path, epochs, lr, hidden, embed_dim,
                         dropout, val_frac, test_frac, verbose)
    raise NotImplementedError("DGL training path not yet implemented — set BACKEND=pyg")


def _train_pyg(data, output_path, epochs, lr, hidden, embed_dim,
               dropout, val_frac, test_frac, verbose):
    train_mask, val_mask, test_mask = temporal_split(data, val_frac, test_frac)

    n_nodes = data.num_nodes
    model   = build_model(NODE_FEATURE_DIM, hidden, embed_dim, dropout)
    opt     = torch.optim.Adam(model.parameters(), lr=lr)

    def _loss_step(mask):
        pos_idx  = mask.nonzero(as_tuple=False).view(-1)
        if pos_idx.numel() == 0:
            return torch.tensor(0.0, requires_grad=True)
        pos_edges = data.edge_index[:, pos_idx]
        neg_edges = _negative_sample_pyg(n_nodes, pos_edges, pos_idx.numel())

        z = model.encode(data.x, data.edge_index[:, mask == False])  # noqa: E712
        pos_pred = model.predict_link(z, pos_edges[0], pos_edges[1])
        neg_pred = model.predict_link(z, neg_edges[0], neg_edges[1])
        labels   = torch.cat([torch.ones_like(pos_pred), torch.zeros_like(neg_pred)])
        preds    = torch.cat([pos_pred, neg_pred])
        return F.binary_cross_entropy(preds, labels)

    best_val   = 0.0
    best_state = model.state_dict()

    for epoch in range(1, epochs + 1):
        model.train()
        opt.zero_grad()
        loss = _loss_step(train_mask)
        loss.backward()
        opt.step()

        if epoch % 10 == 0:
            model.eval()
            with torch.no_grad():
                z = model.encode(data.x, data.edge_index)
            if val_mask.any():
                pos_val = data.edge_index[:, val_mask]
                neg_val = _negative_sample_pyg(n_nodes, pos_val, pos_val.size(1))
                val_auc = _auc_pyg(model, z, pos_val, neg_val)
            else:
                val_auc = 0.5

            if val_auc >= best_val:
                best_val   = val_auc
                best_state = {k: v.clone() for k, v in model.state_dict().items()}

            if verbose:
                print(f"  epoch {epoch:4d}  loss={loss.item():.4f}  val_auc={val_auc:.4f}")

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        z = model.encode(data.x, data.edge_index)

    test_auc = 0.5
    if test_mask.any():
        pos_test = data.edge_index[:, test_mask]
        neg_test = _negative_sample_pyg(n_nodes, pos_test, pos_test.size(1))
        test_auc = _auc_pyg(model, z, pos_test, neg_test)

    if verbose:
        print(f"\nBest val AUC: {best_val:.4f}  |  Test AUC: {test_auc:.4f}")

    config = {
        "in_channels": NODE_FEATURE_DIM,
        "hidden":      hidden,
        "embed_dim":   embed_dim,
        "dropout":     dropout,
    }
    checkpoint = {
        "model_state":  best_state,
        "model_config": config,
        "dealer_ids":   data.dealer_ids,
        "backend":      BACKEND,
        "val_auc":      best_val,
        "test_auc":     test_auc,
    }
    torch.save(checkpoint, output_path)
    if verbose:
        print(f"Checkpoint saved → {output_path}")
    return checkpoint


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",      required=True)
    parser.add_argument("--output",  default="model.pt")
    parser.add_argument("--epochs",  type=int, default=100)
    parser.add_argument("--lr",      type=float, default=0.005)
    args = parser.parse_args()

    train(args.db, args.output, epochs=args.epochs, lr=args.lr)
