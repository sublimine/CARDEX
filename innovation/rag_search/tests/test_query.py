"""Tests for query_engine.py — FAISS search + hard filter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import faiss
import numpy as np
import pytest


def _build_index(listings: list[dict], data_dir: Path) -> None:
    """Build a small FAISS Flat index from fixtures using deterministic embeddings."""
    from indexer import listing_to_text

    texts = [listing_to_text(l) for l in listings]

    # Deterministic embeddings: use text hash as RNG seed for reproducibility.
    vecs = []
    for text in texts:
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(768).astype(np.float32)
        v /= np.linalg.norm(v)
        vecs.append(v)
    vecs_np = np.stack(vecs)

    index = faiss.IndexFlatIP(768)
    index.add(vecs_np)

    faiss.write_index(index, str(data_dir / "faiss_index.bin"))
    id_map = {str(i): l["vehicle_id"] for i, l in enumerate(listings)}
    (data_dir / "id_map.json").write_text(json.dumps(id_map))


def _make_engine(db_path: Path, data_dir: Path, fixtures: list[dict]) -> "QueryEngine":
    from query_engine import QueryEngine

    _build_index(fixtures, data_dir)

    with patch("query_engine.FAISS_INDEX_PATH", data_dir / "faiss_index.bin"), \
         patch("query_engine.ID_MAP_PATH", data_dir / "id_map.json"):

        engine = object.__new__(QueryEngine)
        engine.db_path = db_path
        engine.index_path = data_dir / "faiss_index.bin"
        engine.id_map_path = data_dir / "id_map.json"

        # Mock the embedding model: encode query by hashing to a deterministic vector.
        mock_model = MagicMock()
        def fake_encode(texts, **kwargs):
            vecs = []
            for t in texts:
                rng = np.random.default_rng(abs(hash(t)) % (2**32))
                v = rng.standard_normal(768).astype(np.float32)
                v /= np.linalg.norm(v)
                vecs.append(v)
            return np.stack(vecs)
        mock_model.encode = fake_encode
        engine.model = mock_model

        engine._index = faiss.read_index(str(data_dir / "faiss_index.bin"))
        engine._id_map = {
            int(k): v for k, v in json.loads((data_dir / "id_map.json").read_text()).items()
        }
        return engine


def test_search_returns_results(rag_db, rag_data_dir, fixtures):
    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    results = engine.search("BMW diesel Germany")
    assert len(results) > 0


def test_top5_bmw_de_fixture_present(rag_db, rag_data_dir, fixtures):
    """The query 'BMW diesel Germany' must have a BMW DE fixture in the top-5."""
    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    results = engine.search("BMW diesel Germany")
    top5_ids = {r.vehicle_id for r in results[:5]}
    bmw_de_ids = {
        f["vehicle_id"]
        for f in fixtures
        if f["make"] == "BMW" and f["country"] == "DE"
    }
    assert top5_ids & bmw_de_ids, (
        f"No BMW DE fixture in top-5; top5={top5_ids}, bmw_de={bmw_de_ids}"
    )


def test_country_filter_excludes_other_countries(rag_db, rag_data_dir, fixtures):
    from query_engine import SearchFilters

    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    sf = SearchFilters(country="DE")
    results = engine.search("BMW diesel", filters=sf)
    for r in results:
        assert r.country.upper() == "DE", f"Non-DE result slipped through: {r}"


def test_price_max_filter(rag_db, rag_data_dir, fixtures):
    from query_engine import SearchFilters

    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    sf = SearchFilters(price_max=20000)
    results = engine.search("car", filters=sf)
    for r in results:
        assert r.price_eur <= 20000, f"Price {r.price_eur} exceeds max 20000"


def test_km_max_filter(rag_db, rag_data_dir, fixtures):
    from query_engine import SearchFilters

    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    sf = SearchFilters(km_max=50000)
    results = engine.search("car", filters=sf)
    for r in results:
        assert r.mileage_km <= 50000, f"Mileage {r.mileage_km} exceeds km_max 50000"


def test_empty_index_returns_empty(tmp_path):
    from query_engine import QueryEngine

    engine = object.__new__(QueryEngine)
    engine.db_path = tmp_path / "nonexistent.db"
    engine.index_path = tmp_path / "faiss_index.bin"
    engine.id_map_path = tmp_path / "id_map.json"
    engine._index = None
    engine._id_map = {}
    engine.model = MagicMock()

    results = engine.search("BMW diesel")
    assert results == []


def test_index_size_property(rag_db, rag_data_dir, fixtures):
    engine = _make_engine(rag_db, rag_data_dir, fixtures)
    assert engine.index_size == len(fixtures)
