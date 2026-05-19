"""
AutoScout24 portal scraper — shared engine for all 6 country variants.

Strategy B (2026-05-16):
  curl_cffi AsyncSession(impersonate="chrome", http_version=3)
  "chrome" alias = latest fingerprint in curl_cffi (Chrome 136+).
  Session-level impersonate only — never per-request (breaks JA3 coherence).

URL structure (verified 2026-04-28 against live HTML):
  Search: /lst?atype=C&desc=0&sort=standard&page={N}&year_from={Y}&year_to={Y2}
            &price_to={P}&fuel={F}
  Listings: embedded in Next.js JSON as "url":"/angebote/{slug}-{uuid}"
            NOT in <a href>. Extraction: script[55] JSON body.

Per-country listing path prefixes:
  DE: /angebote/    FR: /annonces/    ES: /anuncios/
  NL: /aanbod/      BE: /annonces/ or /aanbod/    CH: /annonces/ or /angebote/

Pagination: 20 listings/page, max 20 pages (400/segment).
  If a segment hits the cap, it's sub-divided by fuel type.

Softblock detection: CF returns 200 + challenge HTML on warm IPs.
Retry: exponential backoff on 403/429/503 and softblocks.
Rate: jittered sleep (§22 — uniform sleep = bot signal).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from itertools import product
from typing import Any

from curl_cffi.requests import AsyncSession

from scrapers.common.indexer import run_portal

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

log = logging.getLogger(__name__)

_PAGE_SIZE = 20
_MAX_PAGE = 20

# Jittered sleep: base ± 40% — breaks uniform timing signature
_SLEEP_BASE = 1.2
_SLEEP_JITTER = 0.4

# Retry config
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_BASE = 2.0  # seconds, doubled each attempt

_YEAR_BANDS = [
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
]
_PRICE_CEILINGS = [5_000, 10_000, 15_000, 20_000, 30_000, 50_000, 100_000, None]
_FUELS = ["P", "D", "E", "H"]

# HTTP status codes that indicate rate limiting or CF block
_BLOCK_STATUSES = {403, 429, 503}

_CF_MARKERS = [
    "cf-browser-verification",
    "Enable JavaScript and cookies to continue",
    "Just a moment",
    "checking your browser",
    "__cf_chl_",
    "jschl-answer",
    "Attention Required! | Cloudflare",
]


def _build_url(
    base: str,
    year_from: int,
    year_to: int,
    price_to: int | None,
    fuel: str,
    page: int,
) -> str:
    url = f"{base}?atype=C&desc=0&sort=standard&year_from={year_from}&year_to={year_to}&page={page}"
    if price_to is not None:
        url += f"&price_to={price_to}"
    if fuel:
        url += f"&fuel={fuel}"
    return url


def _is_softblocked(html: str) -> bool:
    """Detect CF challenge even when HTTP status is 200."""
    lo = html.lower()
    return any(m.lower() in lo for m in _CF_MARKERS)


def _jitter_sleep() -> float:
    """Return sleep duration with ±40% jitter around base."""
    return _SLEEP_BASE + random.uniform(-_SLEEP_JITTER, _SLEEP_JITTER)


def _extract_listing_urls(html: str, json_re: re.Pattern, base_url: str) -> list[str]:
    """
    Extract listing URLs from AS24 Next.js JSON embedded in HTML.
    Pattern matches relative path inside double-quoted JSON string.
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in json_re.finditer(html):
        path = m.group(1)
        full = base_url + path
        if full not in seen:
            seen.add(full)
            result.append(full)
    return result


async def _fetch_page(
    sess: AsyncSession,
    url: str,
    json_re: re.Pattern,
    base_url: str,
) -> list[str]:
    """Fetch a single page with retry + softblock detection."""
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            r = await sess.get(url, timeout=20)
        except Exception as exc:
            log.debug("fetch error (attempt %d/%d) %s: %s", attempt, _RETRY_ATTEMPTS, url[:80], exc)
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt)
            continue

        if r.status_code in _BLOCK_STATUSES:
            log.debug("HTTP %d (attempt %d/%d) %s", r.status_code, attempt, _RETRY_ATTEMPTS, url[:80])
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt)
            continue

        if r.status_code != 200:
            log.debug("HTTP %d %s", r.status_code, url[:80])
            return []

        html = r.text
        if _is_softblocked(html):
            log.warning("softblock detected (attempt %d/%d) %s", attempt, _RETRY_ATTEMPTS, url[:80])
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt * 2)
            continue

        return _extract_listing_urls(html, json_re, base_url)

    log.warning("all %d attempts failed: %s", _RETRY_ATTEMPTS, url[:80])
    return []


async def _paginate_segment(
    sess: AsyncSession,
    base: str,
    year_from: int,
    year_to: int,
    price_to: int | None,
    fuel: str,
    json_re: re.Pattern,
    base_url: str,
) -> list[str]:
    all_urls: list[str] = []
    for page in range(1, _MAX_PAGE + 1):
        url = _build_url(base, year_from, year_to, price_to, fuel, page)
        urls = await _fetch_page(sess, url, json_re, base_url)
        all_urls.extend(urls)
        await asyncio.sleep(_jitter_sleep())
        if len(urls) < _PAGE_SIZE:
            break
    return all_urls


async def _collect(config: dict[str, Any]) -> list[str]:
    base: str = config["search_base"]
    base_url: str = config["base_url"]
    json_re: re.Pattern = re.compile(config["listing_json_re"], re.IGNORECASE)
    source: str = config["source"]
    country: str = config["country"]

    collected: set[str] = set()
    total_segments = 0
    t0 = time.monotonic()

    # Single session — impersonate at session level, never per-request (JA3 invariant)
    async with AsyncSession(impersonate="chrome", http_version=3) as sess:
        for (year_from, year_to), price_to in product(_YEAR_BANDS, _PRICE_CEILINGS):
            urls = await _paginate_segment(
                sess, base, year_from, year_to, price_to, "", json_re, base_url
            )
            pre = len(collected)
            collected.update(urls)
            total_segments += 1

            # Segment hit the page cap — subdivide by fuel for full coverage
            cap_hit = len(urls) >= _MAX_PAGE * _PAGE_SIZE
            if cap_hit:
                for fuel in _FUELS:
                    fuel_urls = await _paginate_segment(
                        sess, base, year_from, year_to, price_to, fuel, json_re, base_url
                    )
                    collected.update(fuel_urls)
                    total_segments += 1

            log.debug(
                "%s/%s year=%d-%d price_to=%s new=%d total=%d",
                source, country, year_from, year_to, price_to,
                len(collected) - pre, len(collected),
            )

    log.info(
        "%s/%s segments=%d total_urls=%d elapsed=%.1fs",
        source, country, total_segments, len(collected), time.monotonic() - t0,
    )
    return list(collected)


async def run(config: dict[str, Any]) -> None:
    await run_portal(
        source=config["source"],
        country=config["country"],
        domain=config["domain"],
        fetch_all_urls=lambda: _collect(config),
    )
