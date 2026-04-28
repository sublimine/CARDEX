"""
BOVAG member directory — NL national car dealer association.

BOVAG (Bond van Automobielhandelaren en Garagehouders) is the Dutch trade
association. Members are professional car dealers and garages. The public
member search at bovag.nl/leden-zoeken exposes a JSON backend with each
member's website URL, city, postcode, phone.

Usage:
    python -m scrapers.discovery.sources.bovag
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from urllib.parse import urlparse

import asyncpg
import httpx

log = logging.getLogger("bovag")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [bovag] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
}

# BOVAG uses Sitecore XHR endpoints; the member search returns JSON with
# dealers paginated. The real endpoint is discovered by inspecting the
# network tab of bovag.nl/leden-zoeken. Fallback: scrape the HTML result page.
_SEARCH_ENDPOINTS = [
    "https://www.bovag.nl/api/leden/search?pageIndex={page}&pageSize=50",
    "https://www.bovag.nl/leden-zoeken?pageIndex={page}&pageSize=50",
    "https://www.bovag.nl/api/search/members?offset={offset}&limit=50",
]

_DOMAIN_RE = re.compile(r'"website"\s*:\s*"(https?://[^"]+)"', re.IGNORECASE)
_HREF_SITE_RE = re.compile(r'href="(https?://(?!(?:www\.)?bovag)[^"]+)"[^>]*(?:target="_blank"|rel="no)', re.IGNORECASE)


def _apex(url: str) -> str | None:
    try:
        n = urlparse(url).netloc.lower()
    except Exception:
        return None
    if n.startswith("www."):
        n = n[4:]
    if not n:
        return None
    return n


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, http2=True) as client:
        inserted = 0
        seen: set[str] = set()

        # Approach 1: try known JSON endpoints
        for page in range(0, 500):
            any_json = False
            data_rows: list[dict] = []
            for template in _SEARCH_ENDPOINTS:
                url = template.format(page=page, offset=page * 50)
                try:
                    r = await client.get(url, headers=_HDR)
                except Exception:
                    continue
                if r.status_code != 200:
                    continue
                if "application/json" in r.headers.get("content-type", ""):
                    try:
                        payload = r.json()
                    except Exception:
                        continue
                    # find any list inside
                    if isinstance(payload, dict):
                        for key in ("results", "members", "items", "data"):
                            v = payload.get(key)
                            if isinstance(v, list) and v:
                                data_rows = v
                                break
                    elif isinstance(payload, list):
                        data_rows = payload
                    if data_rows:
                        any_json = True
                        break
                else:
                    # HTML fallback — regex-extract external URLs
                    hrefs = _HREF_SITE_RE.findall(r.text)
                    for href in hrefs:
                        dom = _apex(href)
                        if not dom or dom in seen:
                            continue
                        if not dom.endswith(".nl") and not dom.endswith(".be"):
                            continue
                        seen.add(dom)
                        if await _insert(pool, dom, "NL"):
                            inserted += 1
                    if hrefs:
                        any_json = True
                    break

            if not any_json:
                log.warning("bovag page %d: no data — stop", page)
                break

            for row in data_rows:
                site = None
                for k in ("website", "url", "homepage", "webUrl"):
                    if isinstance(row, dict) and row.get(k):
                        site = row[k]
                        break
                if not site:
                    continue
                dom = _apex(site)
                if not dom or dom in seen:
                    continue
                seen.add(dom)
                if await _insert(pool, dom, "NL"):
                    inserted += 1

            if page % 5 == 0:
                log.info("bovag page=%d seen=%d inserted=%d", page, len(seen), inserted)

        log.info("DONE bovag seen=%d inserted=%d", len(seen), inserted)
    await pool.close()


async def _insert(pool: asyncpg.Pool, domain: str, country: str) -> bool:
    try:
        await pool.execute(
            """
            INSERT INTO discovery_candidates
              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
            VALUES ($1,$2,7,'bovag',$3,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'{}'::jsonb)
            ON CONFLICT (domain, country) WHERE domain IS NOT NULL
            DO NOTHING
            """,
            domain, country, f"https://{domain}/",
        )
        return True
    except Exception:
        return False


if __name__ == "__main__":
    asyncio.run(run())
