"""
Trustpilot dealer directory miner.

Trustpilot's category pages list businesses by their canonical domain —
the review URL is literally `/review/<domain.tld>`, so parsing the href
gives us the business website for free.

Per-country pagination via ?country=XX&page=N. Uses curl_cffi chrome124 to
bypass Cloudflare.

Usage:
    python -m scrapers.discovery.sources.trustpilot
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import asyncpg
from curl_cffi.requests import AsyncSession

log = logging.getLogger("trustpilot")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [trustpilot] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_BASE = "https://www.trustpilot.com/categories/car_dealer"

_CATEGORIES = (
    "car_dealer",
    "used_car_dealer",
    "auto_market",
    "car_exporter",
    "auto_broker",
    "car_leasing_service",
    "car_finance_and_loan_company",
    "motor_vehicle_dealer",
)

_COUNTRIES = ("DE", "FR", "ES", "NL", "BE", "CH")

_TLDS_OK = {
    "DE": (".de", ".at"),
    "FR": (".fr",),
    "ES": (".es",),
    "NL": (".nl",),
    "BE": (".be",),
    "CH": (".ch",),
}

_REVIEW_RE = re.compile(r'href="(/review/[a-z0-9.-]+\.[a-z]{2,})"', re.IGNORECASE)

_MAX_PAGES = int(os.environ.get("TP_MAX_PAGES", "500"))


async def _fetch(sess: AsyncSession, url: str) -> str | None:
    try:
        r = await sess.get(url, impersonate="chrome124", timeout=20)
    except Exception as exc:
        log.debug("fetch %s: %s", url, exc)
        return None
    if r.status_code != 200:
        return None
    return r.text


async def _upsert(pool: asyncpg.Pool, domain: str, country: str) -> bool:
    try:
        await pool.execute(
            """
            INSERT INTO discovery_candidates
              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
            VALUES ($1,$2,5,'trustpilot',$3,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'{}'::jsonb)
            ON CONFLICT (domain, country) WHERE domain IS NOT NULL
            DO NOTHING
            """,
            domain, country, f"https://{domain}/",
        )
        return True
    except Exception:
        return False


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    total_ins = 0
    total_seen = 0
    async with AsyncSession() as sess:
        for country in _COUNTRIES:
            tlds = _TLDS_OK[country]
            seen_c: set[str] = set()
            for category in _CATEGORIES:
                for page in range(1, _MAX_PAGES + 1):
                    url = f"https://www.trustpilot.com/categories/{category}?country={country}&page={page}"
                    html = await _fetch(sess, url)
                    if not html:
                        break
                    matches = _REVIEW_RE.findall(html)
                    if not matches:
                        break
                    new_on_page = 0
                    for m in matches:
                        dom = m.replace("/review/", "").strip().lower()
                        if not dom or dom in seen_c:
                            continue
                        # Filter by TLD
                        if not any(dom.endswith(t) for t in tlds):
                            continue
                        seen_c.add(dom)
                        if await _upsert(pool, dom, country):
                            total_ins += 1
                            new_on_page += 1
                    total_seen += new_on_page
                    log.info("%s/%s p=%d new=%d seen_c=%d total_ins=%d",
                             country, category, page, new_on_page, len(seen_c), total_ins)
                    if new_on_page == 0:
                        break
                    await asyncio.sleep(0.5)
            log.info("%s done: seen_domains=%d total_inserted=%d",
                     country, len(seen_c), total_ins)
    log.info("DONE total_seen=%d inserted=%d", total_seen, total_ins)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
