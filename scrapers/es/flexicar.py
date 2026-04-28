"""flexicar.es â€” Playwright DOM. Dealer chain ES."""
from __future__ import annotations
import asyncio, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "flexicar", "ES", "www.flexicar.es"
_BASE = "https://www.flexicar.es"
_API_RE = re.compile(r'flexicar\.es/(?:api|coches)', re.I)
_HREF_RE = re.compile(r'href="(/coches-segunda-mano/[a-z0-9-]+-\d+)"')
_JSON_RE = re.compile(r'"/coches-segunda-mano/[a-z0-9-]+-\d+"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/coches-segunda-mano?page={p}&orden=fecha-desc",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=3000, locale="es-ES",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

