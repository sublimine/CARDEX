"""heycar.com/de â€” Playwright DOM. German listing path: /de/auto/{make}-{model}-{id}."""
from __future__ import annotations
import asyncio, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "heycar_de", "DE", "heycar.com"
_BASE = "https://heycar.com"
_API_RE = re.compile(r'heycar\.com/api|graphql', re.I)
_ID_RE = re.compile(r'"/de/auto/[a-z0-9-]+-[A-Z0-9]{6,}"')
_HREF_RE = re.compile(r'href="(/de/auto/[^"\'?#\s]{10,})"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    for m in _ID_RE.finditer(body):
        path = m.group(0).strip('"')
        urls.add(_BASE + path)
    for m in _HREF_RE.finditer(body):
        urls.add(_BASE + m.group(1))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"https://heycar.com/de/autos?page={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=100, page_wait_ms=3000, locale="de-DE",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

