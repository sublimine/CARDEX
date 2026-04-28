"""coches.com â€” Playwright + XHR. Correct path: /coches-segunda-mano/?page={N}"""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "coches_com", "ES", "www.coches.com"
_BASE = "https://www.coches.com"
_API_RE = re.compile(r'coches\.com/(?:api|coches-segunda-mano)', re.I)
_HREF_RE = re.compile(r'href="(/coches-segunda-mano/[^"\'?#\s]{10,})"')
_JSON_RE = re.compile(r'"/coches-segunda-mano/[^"\'?#\s]{10,}"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _JSON_RE.finditer(raw): urls.add(_BASE + m.group(0).strip('"'))
    except Exception:
        pass
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    for m in _JSON_RE.finditer(body): urls.add(_BASE + m.group(0).strip('"'))
    # Filter: must have depth > /coches-segunda-mano/
    return [u for u in urls if u.count('/') >= 5]

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/coches-segunda-mano/?page={p}",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=300, page_wait_ms=3000, locale="es-ES",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

