"""
kleinanzeigen.de — C2C classifieds DE.

Verified 2026-04-28: HTTP 200, 390KB SSR HTML.
Listing URL format: /s-anzeige/{slug}/{id}-{cat1}-{cat2}
  e.g. /s-anzeige/opel-astra-st.../3362353940-216-2638
  ID has 3+ numeric components separated by dashes.
  Regex: /s-anzeige/{path} where path ends in digits.
"""
from __future__ import annotations

import asyncio
import logging
import re

from curl_cffi.requests import AsyncSession

from scrapers.common.indexer import run_portal

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

log = logging.getLogger(__name__)

_SOURCE = "kleinanzeigen_de"
_COUNTRY = "DE"
_DOMAIN = "www.kleinanzeigen.de"
_BASE = "https://www.kleinanzeigen.de"
# Matches /s-anzeige/{slug}/{numeric-id-components}
# Verified pattern: /s-anzeige/opel-astra-.../3362353940-216-2638
_REL_RE = re.compile(r'href="(/s-anzeige/[^"\'?#\s<>]+-\d+)"')
_SEARCH_TPL = "https://www.kleinanzeigen.de/s-autos/seite:{page}/c216"
_MAX_PAGE = 200
_SLEEP = 1.2


async def _fetch_page(sess: AsyncSession, page: int) -> list[str]:
    url = _SEARCH_TPL.format(page=page)
    try:
        r = await sess.get(url, impersonate="chrome124", timeout=20)
    except Exception as exc:
        log.debug("fetch error page=%d: %s", page, exc)
        return []
    if r.status_code != 200:
        return []
    urls: set[str] = set()
    for m in _REL_RE.finditer(r.text):
        path = m.group(1)
        # Must have numeric ID segment (at least 8 digits total)
        if re.search(r'\d{6,}', path):
            urls.add(_BASE + path)
    return list(urls)


async def _collect() -> list[str]:
    collected: set[str] = set()
    async with AsyncSession() as sess:
        for page in range(1, _MAX_PAGE + 1):
            urls = await _fetch_page(sess, page)
            if not urls:
                break
            prev = len(collected)
            collected.update(urls)
            await asyncio.sleep(_SLEEP)
            if len(collected) == prev:
                break
    log.info("%s/%s total_urls=%d", _SOURCE, _COUNTRY, len(collected))
    return list(collected)


async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())
