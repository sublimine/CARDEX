"""lacentrale.fr â€” Playwright + XHR. CF Turnstile. Listing: /auto-occasion-annonce-{id}.html"""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "lacentrale", "FR", "www.lacentrale.fr"
_BASE = "https://www.lacentrale.fr"
_API_RE = re.compile(r'lacentrale\.fr/(?:api|listing|_next)', re.I)
_LISTING_RE = re.compile(r'"/auto-occasion-annonce-\d+\.html"')

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
        search_url_fn=lambda p: f"{_BASE}/listing?makesModelsCommercialNames=&page={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=300, page_wait_ms=3500, locale="fr-FR",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

