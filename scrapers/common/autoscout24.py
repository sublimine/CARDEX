"""
AutoScout24 portal scraper — shared engine for all 6 country variants.

Verified 2026-04-28 against live AS24 HTML:
  - Search URL: /lst?atype=C&desc=0&sort=standard&page={N}&year_from={Y}&year_to={Y2}&price_to={P}&fuel={F}
  - Listing URLs embedded in Next.js JSON as: "url":"/angebote/{slug}-{uuid}"
  - NOT in <a href> attributes — in script[55] JSON data
  - Correct extraction: r'"(/angebote/[^"\\\\]{20,})"' (double-quoted JSON string)
  - 20 listings per page, page cap = 20 (400 per filter combination)

Per-country listing path prefixes:
  DE: /angebote/    FR: /annonces/    ES: /anuncios/
  NL: /aanbod/      BE: /annonces/ or /aanbod/    CH: /annonces/ or /angebote/

JA3 invariant: single AsyncSession(impersonate="chrome") throughout.
  "chrome" alias = latest Chrome fingerprint in curl_cffi (currently Chrome 136+).
  Never pass impersonate per-request — session-level ensures coherent JA3 across all pages.
"""
from __future__ import annotations

import asyncio
import logging
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
_SLEEP = 1.2

_YEAR_BANDS = [
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
]
_PRICE_CEILINGS = [5_000, 10_000, 15_000, 20_000, 30_000, 50_000, 100_000, None]
_FUELS = ["P", "D", "E", "H"]


def _build_url(base: str, year_from: int, year_to: int, price_to: int | None, fuel: str, page: int) -> str:
    url = f"{base}?atype=C&desc=0&sort=standard&year_from={year_from}&year_to={year_to}&page={page}"
    if price_to is not None:
        url += f"&price_to={price_to}"
    if fuel:
        url += f"&fuel={fuel}"
    return url


def _extract_listing_urls(html: str, json_re: re.Pattern, base_url: str) -> list[str]:
    """
    Extract listing URLs from AS24 Next.js JSON embedded in the HTML.

    Verified pattern: "url":"/angebote/{slug}-{uuid}" in script[55].
    json_re matches the relative path inside the double-quoted JSON string.
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


async def _fetch_page(sess: AsyncSession, url: str, json_re: re.Pattern, base_url: str) -> list[str]:
    try:
        r = await sess.get(url, timeout=20)
    except Exception as exc:
        log.debug("fetch error %s: %s", url[:80], exc)
        return []
    if r.status_code != 200:
        log.debug("HTTP %d %s", r.status_code, url[:80])
        return []
    return _extract_listing_urls(r.text, json_re, base_url)


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
        await asyncio.sleep(_SLEEP)
        if len(urls) < _PAGE_SIZE:
            break
    return all_urls


async def _collect(config: dict[str, Any]) -> list[str]:
    base: str = config["search_base"]
    base_url: str = config["base_url"]
    # Matches listing path as double-quoted JSON string value, e.g. "/angebote/{slug}"
    json_re: re.Pattern = re.compile(config["listing_json_re"], re.IGNORECASE)
    source: str = config["source"]
    country: str = config["country"]

    collected: set[str] = set()
    total_segments = 0
    t0 = time.monotonic()

    async with AsyncSession(impersonate="chrome", http_version=3) as sess:
        for (year_from, year_to), price_to in product(_YEAR_BANDS, _PRICE_CEILINGS):
            urls = await _paginate_segment(sess, base, year_from, year_to, price_to, "", json_re, base_url)
            pre = len(collected)
            collected.update(urls)
            total_segments += 1

            cap_hit = len(urls) >= _MAX_PAGE * _PAGE_SIZE
            if cap_hit:
                for fuel in _FUELS:
                    fuel_urls = await _paginate_segment(
                        sess, base, year_from, year_to, price_to, fuel, json_re, base_url
                    )
                    collected.update(fuel_urls)
                    total_segments += 1

            log.debug(
                "%s/%s year=%d-%d price_to=%s seg=%d total=%d",
                source, country, year_from, year_to, price_to, len(urls), len(collected),
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
