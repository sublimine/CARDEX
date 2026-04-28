"""
Common Crawl domain discovery.

Queries the Common Crawl URL index for automotive-keyword domains per country
TLD. Produces candidate domain dicts — no state, no side effects, no DB writes.

Common Crawl is a monthly snapshot of the public web maintained as free open
data. Each crawl exposes a CDX index endpoint that supports URL wildcards:

    https://index.commoncrawl.org/CC-MAIN-YYYY-WW-index

The caller can pin a specific snapshot via CC_INDEX_URL env var; otherwise
the module resolves the latest available index lazily.

Output shape (one dict per unique domain):

    {
        "domain":  "autohaus-mueller.de",
        "country": "DE",
        "source":  "common_crawl",
        "url":     "https://autohaus-mueller.de/",
        "keyword": "*autohaus*",
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.parse
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

_CC_INDEX_DEFAULT = os.environ.get(
    "CC_INDEX_URL",
    "https://index.commoncrawl.org/CC-MAIN-2026-12-index",
)
_CC_COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"

_COUNTRY_TLDS: dict[str, str] = {
    "DE": "de", "ES": "es", "FR": "fr",
    "NL": "nl", "BE": "be", "CH": "ch",
}

_KEYWORDS_BY_TLD: dict[str, list[str]] = {
    "de": ["*autohaus*", "*autohandel*", "*kfz*", "*fahrzeug*", "*gebrauchtwagen*"],
    "es": ["*concesionario*", "*coches*", "*vehiculos*", "*automovil*", "*compraventa*"],
    "fr": ["*concessionnaire*", "*automobile*", "*voiture*", "*garage-auto*", "*occasion*"],
    "nl": ["*autodealer*", "*autohandel*", "*autobedrijf*", "*occasions*"],
    "be": ["*autodealer*", "*garage-auto*", "*autohandel*"],
    "ch": ["*autohandel*", "*autohaus*", "*garage-auto*", "*occasion*"],
}

# Domains we skip — these are portals/platforms, not individual dealers.
_PORTAL_SKIP = {
    "autoscout24", "mobile.de", "leboncoin", "marktplaats", "2dehands",
    "coches.net", "milanuncios", "wallapop", "kleinanzeigen", "autotrack",
    "gaspedaal", "lacentrale", "paruvendu", "comparis", "tutti",
    "google", "facebook", "instagram", "twitter", "youtube", "tiktok",
    "wikipedia", "ebay", "amazon", "yelp", "linkedin", "pinterest",
}

_REQUEST_INTERVAL = 2.0  # Common Crawl rate limit — 1 request per 2s per IP
_PAGE_LIMIT = 500        # CDX entries per keyword query


class CommonCrawlSource:
    """
    Yields candidate dealer domains from the Common Crawl URL index.

    Usage:
        async with httpx.AsyncClient(timeout=60) as client:
            src = CommonCrawlSource(client)
            async for cand in src.discover("DE"):
                await pg.execute("INSERT INTO discovery_candidates ...", cand)
    """

    def __init__(self, client: httpx.AsyncClient, index_url: str | None = None):
        self._client = client
        self._index_url = index_url or _CC_INDEX_DEFAULT
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def discover(self, country: str) -> AsyncIterator[dict]:
        tld = _COUNTRY_TLDS.get(country)
        if not tld:
            return
        keywords = _KEYWORDS_BY_TLD.get(tld, [])
        if not keywords:
            return

        seen: set[str] = set()
        total = 0

        for keyword in keywords:
            async for cand in self._query_keyword(keyword, tld, country, seen):
                total += 1
                yield cand

        log.info("common_crawl: %s — %d unique candidate domains", country, total)

    async def _query_keyword(
        self,
        keyword: str,
        tld: str,
        country: str,
        seen: set[str],
    ) -> AsyncIterator[dict]:
        await self._throttle()

        params = {
            "url": f"{keyword}.{tld}",
            "output": "json",
            "limit": _PAGE_LIMIT,
            "fl": "url,status,mime",
        }

        try:
            resp = await self._client.get(self._index_url, params=params)
        except Exception as exc:
            log.debug("common_crawl request failed keyword=%s: %s", keyword, exc)
            return

        if resp.status_code == 404:
            return  # no results for this keyword
        if resp.status_code in (502, 503, 504):
            # Common Crawl CDX service is frequently degraded. Log once,
            # skip this keyword, let the rest of the orchestrator proceed.
            log.warning(
                "common_crawl: CDX service degraded (%d) for %s — skipping keyword",
                resp.status_code, keyword,
            )
            return
        if resp.status_code != 200:
            log.debug("common_crawl HTTP %d keyword=%s", resp.status_code, keyword)
            return

        for line in resp.text.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if str(entry.get("status", "")) != "200":
                continue
            if "html" not in (entry.get("mime") or "").lower():
                continue

            url = entry.get("url") or ""
            domain = _extract_domain(url)
            if not domain or domain in seen:
                continue
            if any(p in domain for p in _PORTAL_SKIP):
                continue

            seen.add(domain)
            yield {
                "domain":       domain,
                "country":      country,
                "source_layer": 5,
                "source":       "common_crawl",
                "url":          f"https://{domain}/",
                "name":         None,
                "address":      None,
                "city":         None,
                "postcode":     None,
                "phone":        None,
                "email":        None,
                "lat":          None,
                "lng":          None,
                "registry_id":  None,
                "external_refs": {"keyword": keyword},
            }

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = _REQUEST_INTERVAL - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()


def _extract_domain(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc
