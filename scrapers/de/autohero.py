"""autohero.com/de â€” Playwright + XHR. Listing path: /de/auto/{make}-{model}-{id}."""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "autohero_de", "DE", "www.autohero.com"
_BASE = "https://www.autohero.com"
_API_RE = re.compile(r'autohero\.com/(?:api|graphql|de/search)', re.I)
_HREF_RE = re.compile(r'"/de/auto/[a-z0-9-]+-[A-Z0-9]{6,}(?!/)"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _HREF_RE.finditer(raw):
            urls.add(_BASE + m.group(0).strip('"'))
    except Exception:
        pass
    for m in _HREF_RE.finditer(body):
        urls.add(_BASE + m.group(0).strip('"'))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"https://www.autohero.com/de/search/?page={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=100, page_wait_ms=3000, locale="de-DE",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

