"""Optional LLM reranker using Llama 3.2 3B Q4 via llama-cpp-python.

Enabled when RAG_LLM_RERANK=true.

The reranker receives the natural-language query + top-20 candidate listings
and asks the LLM to score each listing's relevance (0–10) in a single pass
using a structured prompt. Listings are then sorted by LLM score.

RAM: ~2GB (Q4_K_M quantised Llama 3.2 3B).
Latency: ~5–10s per query on 4-core CPU.
"""

from __future__ import annotations

import json
import logging
import re

from config import LLM_MODEL_PATH, LLM_N_CTX, LLM_N_THREADS
from query_engine import SearchResult

log = logging.getLogger("cardex.rag.llm_reranker")

_RERANK_PROMPT = """\
You are a used-car search expert. Given the buyer's query and a list of vehicle listings, score each listing 0–10 for relevance.

Buyer query: {query}

Listings (JSON):
{listings_json}

Return ONLY a JSON array of integers (one score per listing, in the same order).
Example: [8, 3, 7, ...]
"""


def _listing_summary(r: SearchResult) -> dict:
    return {
        "id": r.vehicle_id,
        "make": r.make,
        "model": r.model,
        "year": r.year,
        "km": r.mileage_km,
        "price_eur": r.price_eur,
        "country": r.country,
        "fuel": r.fuel_type,
    }


class LLMReranker:
    """Llama 3.2 3B Q4 reranker (opt-in via RAG_LLM_RERANK=true)."""

    def __init__(self, model_path: str = LLM_MODEL_PATH) -> None:
        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "llama-cpp-python is required for LLM reranking. "
                "Install it with: pip install llama-cpp-python"
            ) from exc

        log.info("Loading LLM reranker: %s", model_path)
        self._llm = Llama(
            model_path=model_path,
            n_ctx=LLM_N_CTX,
            n_threads=LLM_N_THREADS,
            verbose=False,
        )

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """Return results sorted by LLM relevance score (descending)."""
        if not results:
            return results

        listings_json = json.dumps([_listing_summary(r) for r in results], ensure_ascii=False)
        prompt = _RERANK_PROMPT.format(query=query, listings_json=listings_json)

        try:
            out = self._llm(
                prompt,
                max_tokens=len(results) * 5,
                temperature=0.0,
                stop=["\n\n"],
            )
            text = out["choices"][0]["text"].strip()
            scores = _parse_scores(text, len(results))
        except Exception as exc:
            log.warning("LLM reranker failed (%s); returning cosine order", exc)
            return results

        scored = sorted(
            zip(scores, results), key=lambda x: x[0], reverse=True
        )
        return [r for _, r in scored]


def _parse_scores(text: str, n: int) -> list[float]:
    """Extract a JSON int array from LLM output; fall back to zeros."""
    try:
        arr = json.loads(text)
        if isinstance(arr, list) and len(arr) == n:
            return [float(s) for s in arr]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract all numbers from text
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) >= n:
        return [float(x) for x in nums[:n]]

    log.warning("Could not parse LLM scores from: %r", text[:200])
    return [0.0] * n
