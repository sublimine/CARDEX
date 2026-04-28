"""
mobile.de â€” Playwright + XHR interception. Verified 2026-04-28: all static requests
return 2603-char bot challenge. Playwright intercepts real API responses.
API pattern: suchen.mobile.de/api/* or /fahrzeuge/* responses contain listing IDs.
"""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate


_SOURCE, _COUNTRY, _DOMAIN = "mobile_de", "DE", "suchen.mobile.de"
_BASE = "https://suchen.mobile.de"
_API_RE = re.compile(r'suchen\.mobile\.de/(?:api|fahrzeuge)', re.I)
_ID_RE = re.compile(r'/fahrzeuge/details\.html\?id=(\d+)')
_SEARCH = "https://suchen.mobile.de/fahrzeuge/search.html?categories=CAR&isSearchRequest=true&pageNumber={page}&pageSize=50"

def _extract(body: str, url: str) -> list[str]:
    ids: set[str] = set()
    try:
        ids.update(m.group(1) for m in _ID_RE.finditer(json.dumps(json.loads(body))))
    except Exception:
        pass
    ids.update(m.group(1) for m in _ID_RE.finditer(body))
    return [f"{_BASE}/fahrzeuge/details.html?id={i}" for i in ids]

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: _SEARCH.format(page=p),
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=100, page_wait_ms=4000, locale="de-DE",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

