"""
coches.net â€” Playwright + XHR interception.
SPA loads listings via API. Pagination: /segunda-mano/?Section1Id=2500&pg={N}
Listing URL pattern: /segunda-mano/{make}/{model}-{id}.html
"""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "coches_net", "ES", "www.coches.net"
_BASE = "https://www.coches.net"
_API_RE = re.compile(r'coches\.net/(?:api|segunda-mano)', re.I)
_HREF_RE = re.compile(r'href="(/segunda-mano/[^"\'?#\s]{15,}\.html)"')
_JSON_RE = re.compile(r'"/segunda-mano/[^"\'?#\s]{15,}\.html"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _JSON_RE.finditer(raw): urls.add(_BASE + m.group(0).strip('"'))
    except Exception:
        pass
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/segunda-mano/?Section1Id=2500&pg={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=3000, locale="es-ES",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

