"""CARDEX RAG indexer — SQLite → nomic-embed-text → FAISS.

Usage:
    python -m indexer               # full re-index
    python -m indexer --incremental # add only listings not yet in id_map
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import (
    CARDEX_DB_PATH,
    EMBED_BATCH_SIZE,
    EMBED_DIM,
    EMBED_DOC_PREFIX,
    EMBED_MAX_TOKENS,
    EMBED_MODEL,
    FAISS_INDEX_PATH,
    FAISS_NLIST,
    ID_MAP_PATH,
    RAG_DATA_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cardex.rag.indexer")

# ── SQL ───────────────────────────────────────────────────────────────────────

_LISTING_SQL = """
SELECT
    vr.vehicle_id,
    COALESCE(vr.make_canonical, '')   AS make,
    COALESCE(vr.model_canonical, '')  AS model,
    COALESCE(vr.year, 0)              AS year,
    COALESCE(vr.mileage_km, 0)        AS mileage_km,
    COALESCE(vr.fuel_type, '')        AS fuel_type,
    COALESCE(vr.transmission, '')     AS transmission,
    COALESCE(vr.body_type, '')        AS body_type,
    COALESCE(vr.color, '')            AS color,
    COALESCE(vr.power_kw, 0)          AS power_kw,
    CAST(COALESCE(vr.price_gross_eur, 0) AS INTEGER) AS price_eur,
    COALESCE(de.country_code, '')     AS country
FROM vehicle_record vr
LEFT JOIN dealer_entity de ON de.dealer_id = vr.dealer_id
WHERE vr.status NOT IN ('REJECTED', 'DUPLICATE')
"""

# ── Text representation ───────────────────────────────────────────────────────


def listing_to_text(row: dict[str, Any]) -> str:
    """Build the document string for embedding.

    nomic-embed-text-v1.5 uses task-prefixed asymmetric retrieval:
      - documents are prefixed with "search_document: "
      - queries are prefixed with "search_query: "
    """
    parts = [
        EMBED_DOC_PREFIX,
        f"{row['make']} {row['model']}",
        str(row["year"]) if row["year"] else "",
        f"{row['mileage_km']}km" if row["mileage_km"] else "",
        row["fuel_type"],
        row["transmission"],
        row["body_type"],
        f"{row['power_kw']}kW" if row["power_kw"] else "",
        row["color"],
        f"{row['price_eur']}EUR" if row["price_eur"] else "",
        row["country"],
    ]
    text = " ".join(p for p in parts if p)
    # Truncate to approximately EMBED_MAX_TOKENS words (rough char estimate).
    if len(text) > EMBED_MAX_TOKENS * 5:
        text = text[: EMBED_MAX_TOKENS * 5]
    return text


# ── FAISS helpers ─────────────────────────────────────────────────────────────


def _new_index(n_vectors: int) -> faiss.Index:
    """Create an IVF-Flat index if dataset is large enough, else Flat."""
    min_for_ivf = FAISS_NLIST * 39  # FAISS training minimum
    if n_vectors >= min_for_ivf:
        quantizer = faiss.IndexFlatIP(EMBED_DIM)
        index = faiss.IndexIVFFlat(quantizer, EMBED_DIM, FAISS_NLIST, faiss.METRIC_INNER_PRODUCT)
        return index
    log.info(
        "Dataset too small for IVF (%d < %d), using IndexFlatIP", n_vectors, min_for_ivf
    )
    return faiss.IndexFlatIP(EMBED_DIM)


def _load_index() -> tuple[faiss.Index | None, dict[int, str]]:
    """Load index and id_map from disk if they exist."""
    if FAISS_INDEX_PATH.exists() and ID_MAP_PATH.exists():
        index = faiss.read_index(str(FAISS_INDEX_PATH))
        id_map: dict[int, str] = {
            int(k): v for k, v in json.loads(ID_MAP_PATH.read_text()).items()
        }
        return index, id_map
    return None, {}


def _save_index(index: faiss.Index, id_map: dict[int, str]) -> None:
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    ID_MAP_PATH.write_text(json.dumps(id_map))
    log.info(
        "Saved index: %d vectors → %s", index.ntotal, FAISS_INDEX_PATH
    )


# ── Core indexer ──────────────────────────────────────────────────────────────


class Indexer:
    """SQLite → nomic-embed-text → FAISS indexer."""

    def __init__(
        self,
        db_path: Path = CARDEX_DB_PATH,
        embed_model: str = EMBED_MODEL,
    ) -> None:
        self.db_path = db_path
        log.info("Loading embedding model: %s", embed_model)
        self.model = SentenceTransformer(embed_model, trust_remote_code=True)

    # ── Fetch listings ────────────────────────────────────────────────────────

    def _fetch_listings(
        self, skip_ids: set[str] | None = None
    ) -> list[dict[str, Any]]:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(_LISTING_SQL).fetchall()
        con.close()
        listings = [dict(r) for r in rows]
        if skip_ids:
            listings = [l for l in listings if l["vehicle_id"] not in skip_ids]
        return listings

    # ── Embed ─────────────────────────────────────────────────────────────────

    def _embed(self, texts: list[str]) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=EMBED_BATCH_SIZE,
            show_progress_bar=len(texts) > 200,
            normalize_embeddings=True,  # cosine via inner product on normalized vecs
        )
        return embeddings.astype(np.float32)

    # ── Full index ────────────────────────────────────────────────────────────

    def index_full(self) -> int:
        """Re-index all listings from scratch. Returns number of vectors added."""
        t0 = time.monotonic()
        listings = self._fetch_listings()
        if not listings:
            log.warning("No listings found in %s", self.db_path)
            return 0

        log.info("Embedding %d listings (full re-index)...", len(listings))
        texts = [listing_to_text(l) for l in listings]
        vecs = self._embed(texts)

        index = _new_index(len(listings))
        if hasattr(index, "train"):
            log.info("Training IVF index on %d vectors...", len(vecs))
            index.train(vecs)
        index.add(vecs)

        id_map = {i: l["vehicle_id"] for i, l in enumerate(listings)}
        _save_index(index, id_map)
        log.info(
            "Full index complete: %d vectors in %.1fs",
            index.ntotal,
            time.monotonic() - t0,
        )
        return index.ntotal

    # ── Incremental update ────────────────────────────────────────────────────

    def index_incremental(self) -> int:
        """Add only new listings not yet in the index. Returns vectors added."""
        existing_index, id_map = _load_index()
        known_ids = set(id_map.values())

        listings = self._fetch_listings(skip_ids=known_ids)
        if not listings:
            log.info("No new listings to index.")
            return 0

        log.info("Incremental: embedding %d new listings...", len(listings))
        texts = [listing_to_text(l) for l in listings]
        vecs = self._embed(texts)

        if existing_index is None:
            existing_index = _new_index(len(listings))
            if hasattr(existing_index, "train"):
                existing_index.train(vecs)

        start_idx = len(id_map)
        existing_index.add(vecs)
        for i, l in enumerate(listings):
            id_map[start_idx + i] = l["vehicle_id"]

        _save_index(existing_index, id_map)
        log.info("Incremental index: added %d vectors", len(listings))
        return len(listings)


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="CARDEX RAG indexer")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only add listings not yet in the index (default: full re-index)",
    )
    parser.add_argument("--db", default=str(CARDEX_DB_PATH), help="SQLite DB path")
    args = parser.parse_args()

    indexer = Indexer(db_path=Path(args.db))
    if args.incremental:
        n = indexer.index_incremental()
    else:
        n = indexer.index_full()
    print(f"Done. {n} vectors in index.")


if __name__ == "__main__":
    main()
