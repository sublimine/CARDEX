"""CARDEX RAG search API server.

    POST /search  — natural-language search with optional hard filters
    GET  /health  — index status

Run:
    uvicorn serve:app --host 0.0.0.0 --port 8502
    # or: python serve.py
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import (
    API_HOST,
    API_PORT,
    API_RATE_LIMIT,
    LLM_RERANK_ENABLED,
)
from query_engine import QueryEngine, SearchFilters, SearchResult

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cardex.rag.serve")

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{API_RATE_LIMIT}/minute"])

# ── App state (module-level singletons loaded at startup) ─────────────────────

_engine: QueryEngine | None = None
_reranker: Any | None = None
_start_time = time.monotonic()
_last_indexed_at: str | None = None


def _load_engine() -> QueryEngine:
    from config import FAISS_INDEX_PATH, ID_MAP_PATH

    engine = QueryEngine()
    if FAISS_INDEX_PATH.exists():
        import os

        mtime = os.path.getmtime(FAISS_INDEX_PATH)
        global _last_indexed_at
        _last_indexed_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    return engine


def _load_reranker() -> Any:
    if not LLM_RERANK_ENABLED:
        return None
    from llm_reranker import LLMReranker

    try:
        return LLMReranker()
    except Exception as exc:
        log.warning("LLM reranker unavailable (%s); continuing without it", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _engine, _reranker
    log.info("Loading RAG engine...")
    _engine = _load_engine()
    _reranker = _load_reranker()
    log.info("RAG engine ready. LLM rerank: %s", LLM_RERANK_ENABLED)
    yield
    log.info("Shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CARDEX RAG Search",
    description="Natural-language vehicle search via FAISS + nomic-embed-text",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


# ── Request / response models ─────────────────────────────────────────────────


class FilterParams(BaseModel):
    country: str | None = Field(None, description="ISO-3166-1 alpha-2 (DE, FR, NL…)")
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    km_max: int | None = Field(None, ge=0)
    year_min: int | None = Field(None, ge=1900)
    year_max: int | None = Field(None, ge=1900)
    fuel_type: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512, description="Natural-language query")
    filters: FilterParams = Field(default_factory=FilterParams)
    top_k: int = Field(20, ge=1, le=50, description="Maximum results to return")
    llm_rerank: bool = Field(False, description="Enable LLM reranking for this request")


class ListingOut(BaseModel):
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
    extra: dict[str, Any]


class SearchResponse(BaseModel):
    results: list[ListingOut]
    total: int
    query_ms: float
    reranked: bool


class HealthResponse(BaseModel):
    status: str
    index_vectors: int
    last_indexed_at: str | None
    uptime_s: float
    llm_rerank_enabled: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/search", response_model=SearchResponse)
@limiter.limit(f"{API_RATE_LIMIT}/minute")
async def search(request: Request, body: SearchRequest) -> SearchResponse:
    if _engine is None:
        raise HTTPException(status_code=503, detail="RAG engine not ready")

    t0 = time.monotonic()
    sf = SearchFilters(
        country=body.filters.country,
        price_min=body.filters.price_min,
        price_max=body.filters.price_max,
        km_max=body.filters.km_max,
        year_min=body.filters.year_min,
        year_max=body.filters.year_max,
        fuel_type=body.filters.fuel_type,
    )
    results: list[SearchResult] = _engine.search(
        query=body.query,
        filters=sf,
        top_k_return=body.top_k,
    )

    reranked = False
    if body.llm_rerank and _reranker is not None:
        results = _reranker.rerank(body.query, results)
        reranked = True

    listings = [
        ListingOut(
            vehicle_id=r.vehicle_id,
            make=r.make,
            model=r.model,
            year=r.year,
            mileage_km=r.mileage_km,
            price_eur=r.price_eur,
            country=r.country,
            fuel_type=r.fuel_type,
            score=r.score,
            source_url=r.source_url,
            extra=r.extra,
        )
        for r in results
    ]

    return SearchResponse(
        results=listings,
        total=len(listings),
        query_ms=round((time.monotonic() - t0) * 1000, 1),
        reranked=reranked,
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if _engine is not None else "initializing",
        index_vectors=_engine.index_size if _engine else 0,
        last_indexed_at=_last_indexed_at,
        uptime_s=round(time.monotonic() - _start_time, 1),
        llm_rerank_enabled=LLM_RERANK_ENABLED,
    )


@app.post("/reload")
async def reload_index() -> dict[str, str]:
    """Reload the FAISS index from disk after an incremental update."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="RAG engine not ready")
    _engine.reload_index()
    return {"status": "reloaded", "vectors": str(_engine.index_size)}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("serve:app", host=API_HOST, port=API_PORT, reload=False)
