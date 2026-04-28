"""
AutoScout24 dealer directory harvester via curl_cffi (JA3 Chrome impersonation).

httpx/requests get Cloudflare-challenged because of TLS fingerprint mismatch.
curl_cffi speaks real Chrome TLS (JA3 identical to Chrome 120), bypassing the
Cloudflare IM Under Attack barrier. This module scrapes the AS24 dealer
directory per country, follows profile pages, and extracts the external
website URL.

Usage:
    python -m scrapers.discovery.sources.as24_curl_cffi
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import asyncpg
from curl_cffi.requests import AsyncSession

log = logging.getLogger("as24_cc")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [as24_cc] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_COUNTRIES = {
    "DE": "https://www.autoscout24.de/haendler/",
}

_PROFILE_RE = re.compile(
    r'href="(?:https?://www\.autoscout24\.[a-z]{2,3})?(/haendler/[a-z0-9][^"/]+)(?:"|/")',
    re.IGNORECASE,
)

# External website extraction — AS24 profiles embed dealer URL in JSON-LD or anchor
_SITE_RE = re.compile(
    r'"url"\s*:\s*"(https?://(?!(?:www\.)?autoscout24)[^"]+)"'
)
_SITE_RE2 = re.compile(
    r'href="(https?://(?!(?:www\.)?autoscout24)[^"]+)"[^>]*(?:target="_blank"|rel="no)'
)
_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')
_CITY_RE = re.compile(r'"addressLocality"\s*:\s*"([^"]+)"')
_POSTAL_RE = re.compile(r'"postalCode"\s*:\s*"([^"]+)"')

_CONC = int(os.environ.get("AS24_CONC", "8"))
_MAX_PAGES = int(os.environ.get("AS24_MAX_PAGES", "500"))


def _extract_domain(url: str) -> str | None:
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return None
    if net.startswith("www."):
        net = net[4:]
    if not net or "autoscout24" in net:
        return None
    return net


async def _fetch(sess: AsyncSession, url: str) -> str | None:
    try:
        r = await sess.get(url, impersonate="chrome124", timeout=20)
    except Exception as exc:
        log.debug("fetch %s: %s", url, exc)
        return None
    if r.status_code != 200:
        return None
    return r.text


async def _scrape_country(
    sess: AsyncSession,
    pool: asyncpg.Pool,
    country: str,
    dir_url: str,
) -> int:
    base = f"{urlparse(dir_url).scheme}://{urlparse(dir_url).netloc}"
    seen_profiles: set[str] = set()
    written = 0
    page = 1
    while page <= _MAX_PAGES:
        url = dir_url if page == 1 else f"{dir_url}?page={page}"
        html = await _fetch(sess, url)
        if not html:
            log.warning("as24 %s page %d: fetch failed", country, page)
            break
        hrefs = _PROFILE_RE.findall(html)
        fresh = []
        for h in hrefs:
            full = urljoin(base, h)
            canon = full.rstrip("/").lower()
            if canon not in seen_profiles:
                seen_profiles.add(canon)
                fresh.append(full)
        if not fresh:
            log.info("as24 %s page %d: no new profiles — stop", country, page)
            break

        # Fetch profile pages in parallel
        sem = asyncio.Semaphore(_CONC)

        async def _one(p: str) -> dict | None:
            async with sem:
                h = await _fetch(sess, p)
                if not h:
                    return None
                site_match = _SITE_RE.search(h) or _SITE_RE2.search(h)
                if not site_match:
                    return None
                external = site_match.group(1)
                domain = _extract_domain(external)
                if not domain:
                    return None
                return {
                    "domain": domain,
                    "url": external,
                    "name": (_NAME_RE.search(h) or [None, None])[1] if _NAME_RE.search(h) else None,
                    "city": (_CITY_RE.search(h) or [None, None])[1] if _CITY_RE.search(h) else None,
                    "postcode": (_POSTAL_RE.search(h) or [None, None])[1] if _POSTAL_RE.search(h) else None,
                }

        results = await asyncio.gather(*[_one(p) for p in fresh], return_exceptions=True)
        rows = []
        for r in results:
            if isinstance(r, dict):
                rows.append((
                    r["domain"], country, 2, "portal:autoscout24",
                    r["url"], r["name"], None, r["city"], r["postcode"],
                    None, None, None, None, None, "{}",
                ))
        if rows:
            try:
                await pool.executemany(
                    """
                    INSERT INTO discovery_candidates
                      (domain,country,source_layer,source,url,name,address,city,postcode,phone,email,lat,lng,registry_id,external_refs)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                    ON CONFLICT (domain,country) WHERE domain IS NOT NULL DO NOTHING
                    """,
                    rows,
                )
                written += len(rows)
            except Exception as exc:
                log.warning("insert %s page %d: %s", country, page, exc)

        log.info("as24 %s page %d: +%d profiles (total=%d written=%d)", country, page, len(fresh), len(seen_profiles), written)
        page += 1
        await asyncio.sleep(1)  # polite
    log.info("as24 %s DONE — pages=%d written=%d", country, page - 1, written)
    return written


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    total = 0
    async with AsyncSession() as sess:
        for country, dir_url in _COUNTRIES.items():
            try:
                total += await _scrape_country(sess, pool, country, dir_url)
            except Exception as exc:
                log.warning("country %s errored: %s", country, exc)
    log.info("ALL DONE written=%d", total)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
