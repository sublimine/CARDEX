"""CARDEX RAG query engine — natural language → FAISS top-K → filtered results."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import (
    CARDEX_DB_PATH,
    EMBED_DIM,
    EMBED_MODEL,
    EMBED_QUERY_PREFIX,
    FAISS_INDEX_PATH,
    FAISS_NPROBE,
    ID_MAP_PATH,
    LLM_RERANK_ENABLED,
    QUERY_TOP_K_FAISS,
    QUERY_TOP_K_RETURN,
)

log = logging.getLogger("cardex.rag.query_engine")

# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class SearchFilters:
    country: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    km_max: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    fuel_type: str | None = None


@dataclass
class SearchResult:
    vehicle_id: str
    make: str
    model: str
    year: int
    mileage_km: int
    price_eur: float
    country: str
    fuel_type: str
    score: float
    source_url: str
    extra: dict[str, Any] = field(default_factory=dict)


# ── SQL for fetching listing metadata ─────────────────────────────────────────

_FETCH_SQL = """
SELECT
    vr.vehicle_id,
    COALESCE(vr.make_canonical, '')   AS make,
    COALESCE(vr.model_canonical, '')  AS model,
    COALESCE(vr.year, 0)              AS year,
    COALESCE(vr.mileage_km, 0)        AS mileage_km,
    COALESCE(vr.fuel_type, '')        AS fuel_type,
    COALESCE(vr.transmission, '')     AS transmission,
    COALESCE(vr.body_type, '')        AS body_type,
    CAST(COALESCE(vr.price_gross_eur, 0) AS INTEGER) AS price_eur,
    COALESCE(de.country_code, '')     AS country,
    COALESCE(vr.source_url, '')       AS source_url,
    COALESCE(vr.confidence_score, 0)  AS confidence_score
FROM vehicle_record vr
LEFT JOIN dealer_entity de ON de.dealer_id = vr.dealer_id
WHERE vr.vehicle_id IN ({placeholders})
"""


def _fetch_by_ids(
    db_path: Path, vehicle_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not vehicle_ids:
        return {}
    placeholders = ",".join("?" * len(vehicle_ids))
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(_FETCH_SQL.format(placeholders=placeholders), vehicle_ids).fetchall()
    con.close()
    return {r["vehicle_id"]: dict(r) for r in rows}


# ── Filter application ────────────────────────────────────────────────────────


def _passes_filters(row: dict[str, Any], filters: SearchFilters) -> bool:
    if filters.country and row["country"].upper() != filters.country.upper():
        return False
    if filters.price_max and row["price_eur"] > filters.price_max:
        return False
    if filters.price_min and row["price_eur"] < filters.price_min:
        return False
    if filters.km_max and row["mileage_km"] > filters.km_max:
        return False
    if filters.year_min and row["year"] < filters.year_min:
        return False
    if filters.year_max and row["year"] > filters.year_max:
        return False
    if filters.fuel_type and row["fuel_type"].lower() != filters.fuel_type.lower():
        return False
    return True


# ── Query engine ──────────────────────────────────────────────────────────────


class QueryEngine:
    """Embed query → FAISS ANN → hard filter → ranked results."""

    def __init__(
        self,
        db_path: Path = CARDEX_DB_PATH,
        embed_model: str = EMBED_MODEL,
        index_path: Path = FAISS_INDEX_PATH,
        id_map_path: Path = ID_MAP_PATH,
    ) -> None:
        self.db_path = db_path
        self.index_path = index_path
        self.id_map_path = id_map_path

        log.info("Loading embedding model: %s", embed_model)
        self.model = SentenceTransformer(embed_model, trust_remote_code=True)
        self._index: faiss.Index | None = None
        self._id_map: dict[int, str] = {}
        self._load_index()

    def _load_index(self) -> None:
        if self.index_path.exists() and self.id_map_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            if hasattr(self._index, "nprobe"):
                self._index.nprobe = FAISS_NPROBE
            self._id_map = {
                int(k): v
                for k, v in json.loads(self.id_map_path.read_text()).items()
            }
            log.info("Loaded FAISS index: %d vectors", self._index.ntotal)
        else:
            log.warning("FAISS index not found at %s — run indexer first", self.index_path)

    def reload_index(self) -> None:
        """Hot-reload the index from disk (called after incremental update)."""
        self._load_index()

    @property
    def index_size(self) -> int:
        return self._index.ntotal if self._index is not None else 0

    def _embed_query(self, query: str) -> np.ndarray:
        text = EMBED_QUERY_PREFIX + query
        vec = self.model.encode(
            [text], normalize_embeddings=True
        ).astype(np.float32)
        return vec

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        top_k_faiss: int = QUERY_TOP_K_FAISS,
        top_k_return: int = QUERY_TOP_K_RETURN,
    ) -> list[SearchResult]:
        if self._index is None or self._index.ntotal == 0:
            log.warning("Index is empty — run indexer first")
            return []

        t0 = time.monotonic()
        q_vec = self._embed_query(query)

        k = min(top_k_faiss, self._index.ntotal)
        scores, indices = self._index.search(q_vec, k)

        candidate_ids = []
        score_by_id: dict[str, float] = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            vid = self._id_map.get(int(idx))
            if vid:
                candidate_ids.append(vid)
                score_by_id[vid] = float(score)

        rows = _fetch_by_ids(self.db_path, candidate_ids)
        filters = filters or SearchFilters()

        results: list[SearchResult] = []
        for vid in candidate_ids:
            row = rows.get(vid)
            if row is None:
                continue
            if not _passes_filters(row, filters):
                continue
            results.append(
                SearchResult(
                    vehicle_id=vid,
                    make=row["make"],
                    model=row["model"],
                    year=row["year"],
                    mileage_km=row["mileage_km"],
                    price_eur=row["price_eur"],
                    country=row["country"],
                    fuel_type=row["fuel_type"],
                    score=score_by_id[vid],
                    source_url=row["source_url"],
                    extra={
                        "transmission": row["transmission"],
                        "body_type": row["body_type"],
                        "confidence_score": row["confidence_score"],
                    },
                )
            )
            if len(results) >= top_k_return:
                break

        elapsed = time.monotonic() - t0
        log.debug(
            "Query '%s': %d candidates, %d after filter, %.0fms",
            query[:60],
            len(candidate_ids),
            len(results),
            elapsed * 1000,
        )
        return results
