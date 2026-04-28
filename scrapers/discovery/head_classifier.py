"""
HEAD-probe URL classifier — pre-filter listing-vs-category at near-zero cost.

Insight: an individual vehicle listing page weighs 50–500 KB, while a
category/filter page is template-cached at 5–30 KB. A HEAD request reveals
`Content-Length` for ~200 bytes of network I/O, vs ~150 KB for a full GET.
That's 750× more efficient.

This module exposes a single primitive `is_likely_listing(url)` that:
  1. Issues a HEAD with timeout
  2. Reads `Content-Length`
  3. Returns True if size is in the listing range AND status is 200
  4. Returns False for 4xx, 5xx, redirects loops, or sub-listing-size pages

Used by sitemap_bridge to gate URLs BEFORE delegating to the heavy
`_index_source` primitive of the sealed indexer.

Usage:
    from scrapers.discovery.head_classifier import classify_batch
    results = await classify_batch(client, ["https://...", ...])
    # → [("https://...", "listing" | "category" | "dead" | "unknown"), ...]
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_LISTING_MIN_BYTES = 30_000     # below this is template-only
_LISTING_MAX_BYTES = 2_000_000  # above this is unusual / pdf / archive


async def _head_one(client: httpx.AsyncClient, url: str, timeout: float) -> tuple[str, str, int]:
    """Returns (url, classification, size). Classification ∈ listing|category|dead|unknown."""
    try:
        r = await client.head(url, timeout=timeout, follow_redirects=True)
    except Exception:
        return url, "dead", 0

    if r.status_code in (404, 410):
        return url, "dead", 0
    if r.status_code >= 500:
        return url, "unknown", 0
    if r.status_code != 200:
        return url, "unknown", 0

    cl = r.headers.get("content-length")
    if cl is None:
        # Server doesn't expose CL for the HEAD method (some WAFs strip it).
        # Fall through to "unknown" — caller decides whether to GET fallback.
        return url, "unknown", 0
    try:
        size = int(cl)
    except ValueError:
        return url, "unknown", 0

    if size < _LISTING_MIN_BYTES:
        return url, "category", size
    if size > _LISTING_MAX_BYTES:
        return url, "unknown", size
    return url, "listing", size


async def classify_batch(
    client: httpx.AsyncClient,
    urls: list[str],
    concurrency: int = 50,
    timeout: float = 8.0,
) -> list[tuple[str, str, int]]:
    """
    Classify a batch of URLs concurrently. Returns list of
    (url, classification, content_length).
    """
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(u: str) -> tuple[str, str, int]:
        async with sem:
            return await _head_one(client, u, timeout)

    return await asyncio.gather(*(_bounded(u) for u in urls))


__all__ = ["classify_batch", "is_likely_listing"]


async def is_likely_listing(client: httpx.AsyncClient, url: str, timeout: float = 8.0) -> bool:
    _, cls, _ = await _head_one(client, url, timeout)
    return cls == "listing"
