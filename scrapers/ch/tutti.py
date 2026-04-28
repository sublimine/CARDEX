"""tutti.ch — Swiss classifieds. httpx (offset-based pagination)."""
from __future__ import annotations
import asyncio, logging, re
import httpx
from scrapers.common.indexer import run_portal

log = logging.getLogger(__name__)
_SOURCE, _COUNTRY, _DOMAIN = "tutti", "CH", "www.tutti.ch"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_LISTING_RE = re.compile(r'https://www\.tutti\.ch/de/vi/[^"\'&?\s<>]+', re.I)
_REL_RE = re.compile(r'href="(/de/vi/[^"\'&?\s<>]+)"')
_BASE = "https://www.tutti.ch"
_PAGE_SIZE = 30
_TPL = "https://www.tutti.ch/de/q/auto-motorrad/autos?o={offset}"
_MAX_OFFSET = 10_000
_SLEEP = 1.0

async def _collect() -> list[str]:
    collected: set[str] = set()
    async with httpx.AsyncClient(headers={"User-Agent": _UA, "Accept-Language": "de-CH,de;q=0.9"}, timeout=20, follow_redirects=True, http2=True) as cl:
        for offset in range(0, _MAX_OFFSET, _PAGE_SIZE):
            try: r = await cl.get(_TPL.format(offset=offset))
            except: break
            if r.status_code != 200: break
            text = r.text
            urls = set(_LISTING_RE.findall(text)) | {_BASE + m.group(1) for m in _REL_RE.finditer(text)}
            if not urls: break
            prev = len(collected); collected.update(urls)
            await asyncio.sleep(_SLEEP)
            if len(collected) == prev: break
    return list(collected)

async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())
