"""pkw.de â€” Playwright DOM. Listing path: /autos/{make}/{model}/{slug}.html"""
from __future__ import annotations
import asyncio, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import dom_paginate

_SOURCE, _COUNTRY, _DOMAIN = "pkw_de", "DE", "www.pkw.de"
_BASE = "https://www.pkw.de"
_HREF_RE = re.compile(r'href="(/autos/[^"\'?#\s]{15,}\.html)"')
_JSON_RE = re.compile(r'"/autos/[^"\'?#\s]{15,}\.html"')

def _extract(dom: str) -> list[str]:
    urls: set[str] = set()
    for m in _HREF_RE.finditer(dom):
        urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(dom):
        urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await dom_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"https://www.pkw.de/gebrauchtwagensuche/?page={p}",
        extract_urls_fn=_extract,
        max_pages=200, page_wait_ms=3000, locale="de-DE",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

