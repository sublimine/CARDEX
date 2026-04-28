"""gaspedaal.nl â€” Playwright + XHR. DPG Media WAF blocks static clients."""
from __future__ import annotations
import asyncio, json, re
from scrapers.common.indexer import run_portal
from scrapers.common.pw_base import intercept_paginate

_SOURCE, _COUNTRY, _DOMAIN = "gaspedaal", "NL", "www.gaspedaal.nl"
_BASE = "https://www.gaspedaal.nl"
_API_RE = re.compile(r'gaspedaal\.nl/(?:api|occasion)', re.I)
_HREF_RE = re.compile(r'href="(/[a-z][^"\'?#\s/]+/[^"\'?#\s/]+/[^"\'?#\s]+-\d+)"')
_JSON_RE = re.compile(r'"/[a-z][^"\'?#\s/]+/[^"\'?#\s/]+/[^"\'?#\s]+-\d+"')

def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _JSON_RE.finditer(raw):
            path = m.group(0).strip('"')
            if path.count('/') >= 3: urls.add(_BASE + path)
    except Exception:
        pass
    for m in _HREF_RE.finditer(body): urls.add(_BASE + m.group(1))
    return list(urls)

async def _collect() -> list[str]:
    return await intercept_paginate(
        source=_SOURCE, country=_COUNTRY,
        search_url_fn=lambda p: f"{_BASE}/occasion?page={p}&sorteer=datum_desc",
        api_pattern=_API_RE, extract_urls_fn=_extract,
        max_pages=300, page_wait_ms=3000, locale="nl-NL",
    )

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

