"""comparis.ch â€” Playwright + XHR. CF blocks all static clients."""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "comparis", "CH", "www.comparis.ch"
_BASE = "https://www.comparis.ch"
_API_RE = re.compile(r'comparis\.ch/(?:api|carfinder)', re.I)
_HREF_RE = re.compile(r'href="(/carfinder/markt/details[^"\'?#\s]{5,})"')
_JSON_RE = re.compile(r'"/carfinder/markt/details[^"\'?#\s]{5,}"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _JSON_RE.finditer(raw): urls.add(_BASE + m.group(0).strip('"'))
    except Exception: pass
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/carfinder/?page={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=4000, locale="de-CH",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

