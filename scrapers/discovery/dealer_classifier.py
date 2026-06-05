"""
Dealer website classifier.

Reads discovery_candidates where domain IS NOT NULL and not yet profiled.
For each domain:
  1. Fetch /robots.txt  — respect crawl rules
  2. Fetch homepage     — detect CMS, find inventory links
  3. Probe /sitemap.xml — estimate listing count
  4. Classify: has_inventory, cms_type, estimated_listings, tier
  5. Upsert to dealer_profile

Concurrency: asyncio.Semaphore(CLASSIFIER_CONCURRENCY).
Entry point: python -m scrapers.discovery.dealer_classifier
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_CONCURRENCY = int(os.environ.get("CLASSIFIER_CONCURRENCY", "20"))
_TIMEOUT = float(os.environ.get("CLASSIFIER_TIMEOUT", "15"))
_BATCH = int(os.environ.get("CLASSIFIER_BATCH", "500"))

_UA = "CardexBot/1.0 (+https://cardex.io/bot)"
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "en,fr;q=0.9,de;q=0.8,es;q=0.7,nl;q=0.6",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

# Inventory path fragment patterns
_INVENTORY_RE = re.compile(
    r"/(stock|vehicles?|occasion|gebrauchtwagen|occasions?|voitures?|coches?"
    r"|auto|voorraad|inventory|cars?|flotte|used|neuf|gebraucht|annonces|furgonetas?)"
    r"(?:[/\-?]|$)",
    re.IGNORECASE,
)

# CMS fingerprints: (name, body_regex, response_header_key)
_CMS_SIGS: list[tuple[str, str | None, str | None]] = [
    ("dealerk",    r"cdn\.dealerk\.com|motorK|dealerK",      None),
    ("wordpress",  r"wp-content/|wp-json/|wp-includes/",     None),
    ("nextjs",     r"__NEXT_DATA__",                          None),
    ("nuxtjs",     r"__NUXT__|/_nuxt/",                       None),
    ("wix",        r"wixstatic\.com|static\.wixstatic\.com",  "x-wix-rendered-at"),
    ("prestashop", r"prestashop|id_product=|/modules/ps_",    None),
    ("shopify",    r"cdn\.shopify\.com|Shopify\.theme",        None),
]
_CMS_RE: list[tuple[str, re.Pattern[str] | None, str | None]] = [
    (name, re.compile(pat, re.IGNORECASE) if pat else None, hdr)
    for name, pat, hdr in _CMS_SIGS
]


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS dealer_profile (
    id                  BIGSERIAL PRIMARY KEY,
    domain              TEXT NOT NULL,
    country             CHAR(2),
    has_inventory       BOOLEAN NOT NULL DEFAULT FALSE,
    cms_type            TEXT,
    inventory_urls      TEXT[] NOT NULL DEFAULT '{}',
    estimated_listings  INT NOT NULL DEFAULT 0,
    tier                TEXT CHECK (tier IN ('T0','T1','T2','T3')),
    robots_txt          TEXT,
    classified_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (domain)
);
CREATE INDEX IF NOT EXISTS idx_dp_country ON dealer_profile (country);
CREATE INDEX IF NOT EXISTS idx_dp_tier    ON dealer_profile (tier) WHERE tier IS NOT NULL;
"""


async def _ensure_schema(pool: Any) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_DDL)


# ─────────────────────────────────────────────────────────────────────────────
# Classification logic (pure — importable without asyncpg)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    domain: str
    country: str
    has_inventory: bool = False
    cms_type: str = "custom"
    inventory_urls: list[str] = field(default_factory=list)
    estimated_listings: int = 0
    tier: str | None = None
    robots_txt: str | None = None


def _detect_cms(html: str, headers: httpx.Headers) -> str:
    for name, body_re, hdr_key in _CMS_RE:
        if hdr_key and headers.get(hdr_key):
            return name
        if body_re and body_re.search(html):
            return name
    return "custom"


def _find_inventory_links(html: str, base_url: str) -> list[str]:
    base_netloc = urllib.parse.urlparse(base_url).netloc
    seen: set[str] = set()
    result: list[str] = []
    for m in re.finditer(r'href=["\']([^"\']{5,300})["\']', html, re.IGNORECASE):
        href = m.group(1).strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            full = urllib.parse.urljoin(base_url, href)
        except ValueError:
            continue
        if urllib.parse.urlparse(full).netloc != base_netloc:
            continue
        if _INVENTORY_RE.search(full) and full not in seen:
            seen.add(full)
            result.append(full)
            if len(result) >= 10:
                break
    return result


def _count_inventory_in_sitemap(sitemap_xml: str) -> int:
    return len(_INVENTORY_RE.findall(sitemap_xml))


def _assign_tier(r: ClassificationResult) -> str:
    if r.cms_type == "dealerk":
        return "T0"
    if r.estimated_listings >= 50 or (r.cms_type == "wordpress" and r.has_inventory):
        return "T1"
    if r.has_inventory and r.estimated_listings >= 10:
        return "T2"
    return "T3"


# ─────────────────────────────────────────────────────────────────────────────
# Async helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_robots(
    client: httpx.AsyncClient, base_url: str
) -> tuple[bool, str | None]:
    robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
    try:
        r = await client.get(robots_url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return True, None
        body = r.text
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        return parser.can_fetch(_UA, base_url), body
    except Exception:
        return True, None


async def classify_domain(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    domain: str,
    country: str,
) -> ClassificationResult:
    res = ClassificationResult(domain=domain, country=country)
    base_url = f"https://{domain}/"

    async with sem:
        allowed, robots_body = await _fetch_robots(client, base_url)
        res.robots_txt = robots_body
        if not allowed:
            return res

        try:
            resp = await client.get(base_url, timeout=_TIMEOUT)
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.TooManyRedirects,
            httpx.RemoteProtocolError,
            Exception,
        ):
            return res

        if resp.status_code not in (200, 203):
            return res
        html = resp.text
        if len(html) < 200:
            return res

        res.cms_type = _detect_cms(html, resp.headers)

        inv_links = _find_inventory_links(html, str(resp.url))
        if inv_links:
            res.has_inventory = True
            res.inventory_urls = inv_links

        try:
            sm_resp = await client.get(
                urllib.parse.urljoin(base_url, "/sitemap.xml"), timeout=_TIMEOUT
            )
            if sm_resp.status_code == 200:
                count = _count_inventory_in_sitemap(sm_resp.text)
                if count > 0:
                    res.has_inventory = True
                    res.estimated_listings = count
        except Exception:
            pass

        res.tier = _assign_tier(res)
        return res


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_unclassified(pool: Any, limit: int) -> list[tuple[str, str]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dc.domain, dc.country
              FROM discovery_candidates dc
              LEFT JOIN dealer_profile dp ON dp.domain = dc.domain
             WHERE dc.domain IS NOT NULL
               AND dp.domain IS NULL
             ORDER BY dc.first_seen DESC
             LIMIT $1
            """,
            limit,
        )
    return [(r["domain"], r["country"]) for r in rows]


async def _upsert(pool: Any, r: ClassificationResult) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO dealer_profile
                (domain, country, has_inventory, cms_type, inventory_urls,
                 estimated_listings, tier, robots_txt, classified_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),NOW())
            ON CONFLICT (domain) DO UPDATE SET
                has_inventory      = EXCLUDED.has_inventory,
                cms_type           = EXCLUDED.cms_type,
                inventory_urls     = EXCLUDED.inventory_urls,
                estimated_listings = EXCLUDED.estimated_listings,
                tier               = EXCLUDED.tier,
                robots_txt         = EXCLUDED.robots_txt,
                updated_at         = NOW()
            """,
            r.domain, r.country, r.has_inventory, r.cms_type,
            r.inventory_urls, r.estimated_listings, r.tier, r.robots_txt,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    import asyncpg

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = await asyncpg.create_pool(_DB_URL, min_size=2, max_size=8)
    try:
        await _ensure_schema(pool)
        rows = await _fetch_unclassified(pool, _BATCH)
        if not rows:
            log.info("No unclassified domains — exiting")
            return
        log.info("Classifying %d domains (concurrency=%d)", len(rows), _CONCURRENCY)
        t0 = time.monotonic()
        sem = asyncio.Semaphore(_CONCURRENCY)
        async with httpx.AsyncClient(
            headers=_HEADERS,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=_CONCURRENCY + 5,
                max_keepalive_connections=10,
            ),
        ) as client:
            tasks = [classify_domain(client, sem, dom, ctry) for dom, ctry in rows]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        ok = err = 0
        for res in results:
            if isinstance(res, Exception):
                log.warning("classify error: %s", res)
                err += 1
                continue
            await _upsert(pool, res)  # type: ignore[arg-type]
            ok += 1

        log.info(
            "DONE classified=%d errors=%d elapsed=%.1fs",
            ok, err, time.monotonic() - t0,
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
