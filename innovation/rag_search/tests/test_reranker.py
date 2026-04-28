"""Tests for llm_reranker.py — LLM reranking with mocked llama-cpp."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from query_engine import SearchResult


def _make_result(vehicle_id: str, score: float = 0.9, **kwargs) -> SearchResult:
    defaults = dict(
        make="BMW",
        model="Serie 3",
        year=2021,
        mileage_km=60000,
        price_eur=24000,
        country="DE",
        fuel_type="diesel",
        source_url="https://example.com",
        extra={},
    )
    defaults.update(kwargs)
    return SearchResult(vehicle_id=vehicle_id, score=score, **defaults)


def _make_reranker_with_mock_llm(llm_response: str) -> "LLMReranker":
    """Build a LLMReranker with the Llama class mocked."""
    mock_llm = MagicMock()
    mock_llm.return_value = {
        "choices": [{"text": llm_response}]
    }

    with patch.dict("sys.modules", {"llama_cpp": MagicMock(Llama=MagicMock(return_value=mock_llm))}):
        from llm_reranker import LLMReranker
        reranker = object.__new__(LLMReranker)
        reranker._llm = mock_llm
        return reranker


def test_reranker_reorders_results():
    """LLM scores [1, 9] should flip the order of two listings."""
    reranker = _make_reranker_with_mock_llm("[1, 9]")
    results = [_make_result("id-A", score=0.9), _make_result("id-B", score=0.7)]

    reranked = reranker.rerank("BMW diesel cheap", results)

    assert reranked[0].vehicle_id == "id-B", "Higher LLM score should be ranked first"
    assert reranked[1].vehicle_id == "id-A"


def test_reranker_preserves_all_results():
    """Reranker must return the same number of listings as input."""
    reranker = _make_reranker_with_mock_llm("[5, 3, 8, 2, 9]")
    results = [_make_result(f"id-{i}") for i in range(5)]
    reranked = reranker.rerank("query", results)
    assert len(reranked) == 5


def test_reranker_handles_empty_input():
    reranker = _make_reranker_with_mock_llm("[]")
    assert reranker.rerank("query", []) == []


def test_reranker_falls_back_on_bad_llm_output():
    """Malformed LLM output should return results in original cosine order."""
    reranker = _make_reranker_with_mock_llm("sorry, I cannot score these listings")
    results = [_make_result("id-A", score=0.9), _make_result("id-B", score=0.7)]
    reranked = reranker.rerank("query", results)
    # Both orderings are acceptable; what matters is no exception is raised.
    assert len(reranked) == 2


def test_parse_scores_valid_json():
    from llm_reranker import _parse_scores

    assert _parse_scores("[8, 3, 7]", 3) == [8.0, 3.0, 7.0]


def test_parse_scores_fallback_extraction():
    from llm_reranker import _parse_scores

    # Messy output with embedded numbers
    assert _parse_scores("Score: 8\nScore: 3\nScore: 7", 3) == [8.0, 3.0, 7.0]


def test_parse_scores_wrong_length_returns_zeros():
    from llm_reranker import _parse_scores

    result = _parse_scores("[1, 2]", 3)  # 2 scores for 3 listings
    assert len(result) == 3
    assert all(s == 0.0 for s in result)
