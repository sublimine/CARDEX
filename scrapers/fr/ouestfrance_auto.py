"""ouestfrance-auto.com â€” Playwright DOM. Returns iframe challenge to static requests."""
from __future__ import annotations
import asyncio, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import dom_paginate

_SOURCE, _COUNTRY, _DOMAIN = "ouestfrance_auto", "FR", "www.ouestfrance-auto.com"
_BASE = "https://www.ouestfrance-auto.com"
_HREF_RE = re.compile(r'href="(/auto/voiture/[^"\'?#\s]+/\d+/)"')
_JSON_RE = re.compile(r'"/auto/voiture/[^"\'?#\s]+/\d+/"')

def _extract(dom: str) -> list[str]:
    urls: set[str] = set()
    for m in _HREF_RE.finditer(dom): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(dom): urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await dom_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/auto/?page={p}&tri=date_desc",
        extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=4000, locale="fr-FR",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

