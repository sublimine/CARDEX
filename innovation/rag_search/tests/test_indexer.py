"""Tests for indexer.py — SQLite → FAISS pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_indexer(db_path: Path, data_dir: Path) -> "Indexer":
    """Build an Indexer with mocked embedding model to avoid downloading weights."""
    from indexer import Indexer

    with patch("indexer.FAISS_INDEX_PATH", data_dir / "faiss_index.bin"), \
         patch("indexer.ID_MAP_PATH", data_dir / "id_map.json"), \
         patch("indexer.RAG_DATA_DIR", data_dir):
        idx = object.__new__(Indexer)
        idx.db_path = db_path

        # Replace the real SentenceTransformer with a mock that returns
        # deterministic random embeddings (768 dims, L2-normalized).
        mock_model = MagicMock()
        def fake_encode(texts, **kwargs):
            rng = np.random.default_rng(abs(hash(str(texts))) % (2**32))
            vecs = rng.standard_normal((len(texts), 768)).astype(np.float32)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            return vecs / norms
        mock_model.encode = fake_encode
        idx.model = mock_model
        return idx


def test_full_index_creates_correct_size(rag_db, rag_data_dir, fixtures):
    """Indexing all fixtures should produce an index with len(fixtures) vectors."""
    from indexer import Indexer, _load_index, _save_index
    import faiss

    with patch("indexer.FAISS_INDEX_PATH", rag_data_dir / "faiss_index.bin"), \
         patch("indexer.ID_MAP_PATH", rag_data_dir / "id_map.json"), \
         patch("indexer.RAG_DATA_DIR", rag_data_dir):

        idx = _make_indexer(rag_db, rag_data_dir)

        n = idx.index_full()

    assert n == len(fixtures), f"Expected {len(fixtures)} vectors, got {n}"


def test_full_index_id_map_covers_all_ids(rag_db, rag_data_dir, fixtures):
    """Every fixture vehicle_id must appear in the id_map after indexing."""
    with patch("indexer.FAISS_INDEX_PATH", rag_data_dir / "faiss_index.bin"), \
         patch("indexer.ID_MAP_PATH", rag_data_dir / "id_map.json"), \
         patch("indexer.RAG_DATA_DIR", rag_data_dir):

        idx = _make_indexer(rag_db, rag_data_dir)
        idx.index_full()

        id_map_path = rag_data_dir / "id_map.json"
        assert id_map_path.exists()
        id_map = json.loads(id_map_path.read_text())
        indexed_ids = set(id_map.values())

    expected_ids = {f["vehicle_id"] for f in fixtures}
    assert expected_ids == indexed_ids


def test_index_file_persisted(rag_db, rag_data_dir):
    """faiss_index.bin must exist on disk after indexing."""
    with patch("indexer.FAISS_INDEX_PATH", rag_data_dir / "faiss_index.bin"), \
         patch("indexer.ID_MAP_PATH", rag_data_dir / "id_map.json"), \
         patch("indexer.RAG_DATA_DIR", rag_data_dir):

        idx = _make_indexer(rag_db, rag_data_dir)
        idx.index_full()

    assert (rag_data_dir / "faiss_index.bin").exists()


def test_incremental_adds_only_new(rag_db, rag_data_dir, fixtures):
    """Incremental update should add 0 vectors when all listings already indexed."""
    with patch("indexer.FAISS_INDEX_PATH", rag_data_dir / "faiss_index.bin"), \
         patch("indexer.ID_MAP_PATH", rag_data_dir / "id_map.json"), \
         patch("indexer.RAG_DATA_DIR", rag_data_dir):

        idx = _make_indexer(rag_db, rag_data_dir)
        idx.index_full()
        n_added = idx.index_incremental()

    assert n_added == 0, "Incremental after full-index should add 0 vectors"


def test_listing_to_text_contains_key_fields(fixtures):
    """listing_to_text should include make, model, country, and price."""
    from indexer import listing_to_text

    f = fixtures[0]  # BMW Serie 3 DE
    text = listing_to_text(f)
    assert "BMW" in text
    assert "Serie 3" in text
    assert "DE" in text
    assert "EUR" in text
    assert text.startswith("search_document:")
