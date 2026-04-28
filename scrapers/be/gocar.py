"""gocar.be â€” Playwright DOM. CF challenge blocks static clients."""
from __future__ import annotations
import asyncio, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "gocar", "BE", "www.gocar.be"
_BASE = "https://www.gocar.be"
_API_RE = re.compile(r'gocar\.be/(?:api|voiture)', re.I)
_HREF_RE = re.compile(r'href="(/voiture-occasion/[^"\'?#\s]{10,})"')
_JSON_RE = re.compile(r'"/voiture-occasion/[^"\'?#\s]{10,}"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    return [u for u in urls if u.count('/') >= 5]

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/voitures-occasions?page={p}&tri=date_desc",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=3500, locale="fr-BE",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

