"""largus.fr â€” Playwright + XHR. CF Turnstile. Listing: /voiture-occasion-{slug}-{id}.html"""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "largus_fr", "FR", "www.largus.fr"
_BASE = "https://www.largus.fr"
_API_RE = re.compile(r'largus\.fr/(?:api|voitures)', re.I)
_LISTING_RE = re.compile(r'"/voiture-occasion-[^"\'?#\s]+-\d+\.html"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _LISTING_RE.finditer(raw): urls.add(_BASE + m.group(0).strip('"'))
    except Exception:
        pass
    for m in _LISTING_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/voitures-occasion/page-{p}.html",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=300, page_wait_ms=3500, locale="fr-FR",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

