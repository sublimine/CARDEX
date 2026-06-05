"""
Discovery frontier runner.

Consumes crawl_frontier rows scheduled for crawl. For each row:
  1. Resolve starting URLs from dealer_profile.inventory_urls (platform = domain).
  2. Fetch each page; call meili_enricher.extract() to detect vehicle detail pages.
  3. Follow pagination links (multilingual: next/suivant/weiter/volgende/mehr anzeigen).
  4. Collect all vehicle detail URLs; feed to indexer.delta().
  5. Update Thompson Sampling (alpha/beta/priority_score) based on vehicles found.
  6. Respect robots.txt (domain cache), per-domain rate limits, circuit breakers.

Entry point: python -m scrapers.discovery.frontier_runner
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

from scrapers.discovery.meili_enricher import extract
from scrapers.common.indexer import delta, ensure_schema, make_pg, make_redis

log = logging.getLogger(__name__)

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_CONCURRENCY = int(os.environ.get("FRONTIER_CONCURRENCY", "10"))
_TIMEOUT = float(os.environ.get("FRONTIER_TIMEOUT", "20"))
_MAX_PAGES = int(os.environ.get("FRONTIER_MAX_PAGES", "50"))
_RATE_DELAY_S = float(os.environ.get("FRONTIER_RATE_DELAY", "1.0"))
_BATCH = int(os.environ.get("FRONTIER_BATCH", "200"))

_CB_FAIL_THRESHOLD = 3
_CB_OPEN_DURATION_S = 300.0

_UA = "CardexBot/1.0 (+https://cardex.io/bot)"
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "en,fr;q=0.9,de;q=0.8,es;q=0.7,nl;q=0.6",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

# Multilingual "next page" link text
_NEXT_PAGE_RE = re.compile(
    r"\b(next|suivant|weiter|volgende|siguiente|avanti|prochain|nächste|næste)\b"
    r"|›\s*$|»\s*$|→\s*$"
    r"|\bnext\s+page\b"
    r"|\bmehr\s+anzeigen\b"
    r"|\bvoir\s+plus\b"
    r"|\bload\s+more\b",
    re.IGNORECASE,
)

# Vehicle detail page URL signals
_DETAIL_RE = re.compile(
    r"/(?:annonce|vehicle|voiture|coche|auto|fiche|detail|fahrzeug|wagen|car"
    r"|listing|occasion|vo|vn|stock-detail|used-car|gebraucht)[-_/]?\w",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Per-domain in-memory state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _DomainState:
    last_request_at: float = 0.0
    failure_count: int = 0
    circuit_open_until: float = 0.0
    robots: urllib.robotparser.RobotFileParser | None = None
    robots_loaded: bool = False


_domain_states: dict[str, _DomainState] = {}


def _get_state(domain: str) -> _DomainState:
    if domain not in _domain_states:
        _domain_states[domain] = _DomainState()
    return _domain_states[domain]


def _circuit_is_open(domain: str) -> bool:
    st = _get_state(domain)
    now = time.monotonic()
    if st.circuit_open_until > now:
        return True
    if st.circuit_open_until > 0:
        # Half-open: allow one probe, reset counters
        st.circuit_open_until = 0.0
        st.failure_count = 0
    return False


def _record_failure(domain: str) -> None:
    st = _get_state(domain)
    st.failure_count += 1
    if st.failure_count >= _CB_FAIL_THRESHOLD:
        st.circuit_open_until = time.monotonic() + _CB_OPEN_DURATION_S
        log.warning("circuit OPEN domain=%s failures=%d", domain, st.failure_count)


def _record_success(domain: str) -> None:
    st = _get_state(domain)
    st.failure_count = 0
    st.circuit_open_until = 0.0


async def _rate_limit(domain: str) -> None:
    st = _get_state(domain)
    elapsed = time.monotonic() - st.last_request_at
    if elapsed < _RATE_DELAY_S:
        await asyncio.sleep(_RATE_DELAY_S - elapsed)
    st.last_request_at = time.monotonic()


async def _ensure_robots(
    client: httpx.AsyncClient, domain: str, base_url: str
) -> urllib.robotparser.RobotFileParser | None:
    st = _get_state(domain)
    if st.robots_loaded:
        return st.robots
    st.robots_loaded = True
    try:
        r = await client.get(
            urllib.parse.urljoin(base_url, "/robots.txt"), timeout=_TIMEOUT
        )
        if r.status_code == 200:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(r.text.splitlines())
            st.robots = parser
    except Exception:
        pass
    return st.robots


def _robots_allow(
    robots: urllib.robotparser.RobotFileParser | None, url: str
) -> bool:
    return True if robots is None else robots.can_fetch(_UA, url)


# ─────────────────────────────────────────────────────────────────────────────
# Link extraction (pure — testable without network)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_links(html: str, base_url: str) -> tuple[list[str], list[str]]:
    """Returns (vehicle_detail_urls, next_page_urls) from an HTML page."""
    base_netloc = urllib.parse.urlparse(base_url).netloc
    detail_urls: list[str] = []
    next_urls: list[str] = []

    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']{5,500})["\'][^>]*>(.*?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        href = m.group(1).strip()
        link_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            full = urllib.parse.urljoin(base_url, href)
        except ValueError:
            continue
        if urllib.parse.urlparse(full).netloc != base_netloc:
            continue

        if _NEXT_PAGE_RE.search(link_text):
            if full not in next_urls:
                next_urls.append(full)
        elif _DETAIL_RE.search(full):
            if full not in detail_urls:
                detail_urls.append(full)

    return detail_urls, next_urls


# ─────────────────────────────────────────────────────────────────────────────
# Crawl logic
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _CrawlResult:
    vehicle_urls: list[str] = field(default_factory=list)
    pages_crawled: int = 0
    vehicles_found: int = 0


async def _crawl_segment(
    client: httpx.AsyncClient,
    start_urls: list[str],
    domain: str,
) -> _CrawlResult:
    result = _CrawlResult()
    robots = await _ensure_robots(client, domain, f"https://{domain}/")

    visited: set[str] = set()
    queue: list[str] = list(start_urls)
    vehicle_urls: set[str] = set()

    while queue and result.pages_crawled < _MAX_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        if not _robots_allow(robots, url):
            continue
        if _circuit_is_open(domain):
            log.warning("circuit open domain=%s — aborting segment", domain)
            break

        visited.add(url)
        await _rate_limit(domain)

        try:
            resp = await client.get(url, timeout=_TIMEOUT)
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.TooManyRedirects,
            Exception,
        ) as exc:
            log.debug("fetch error %s: %s", url, exc)
            _record_failure(domain)
            continue

        result.pages_crawled += 1

        if resp.status_code in (429, 503):
            _record_failure(domain)
            log.warning("rate-limited domain=%s status=%d", domain, resp.status_code)
            await asyncio.sleep(30.0)
            continue
        if resp.status_code != 200:
            continue

        html = resp.text
        if len(html) < 200:
            continue

        _record_success(domain)

        # URL pattern decides page type: detail pages are enriched directly,
        # listing pages are mined for links + pagination.
        if _DETAIL_RE.search(url):
            doc, sold = extract(html, url)
            if not sold:
                vehicle_urls.add(url)
                result.vehicles_found += 1
        else:
            detail_urls, next_page_urls = _extract_links(html, str(resp.url))
            for du in detail_urls:
                vehicle_urls.add(du)
            result.vehicles_found += len(detail_urls)
            for nu in next_page_urls:
                if nu not in visited:
                    queue.append(nu)

    result.vehicle_urls = list(vehicle_urls)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Thompson Sampling update
# ─────────────────────────────────────────────────────────────────────────────

async def _update_thompson(pool: Any, row_id: int, vehicles_found: int) -> None:
    """Increment alpha on success, beta on zero-yield; recompute priority_score."""
    alpha_inc = 1 if vehicles_found > 0 else 0
    beta_inc = 0 if vehicles_found > 0 else 1
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE crawl_frontier SET
                thompson_alpha  = thompson_alpha + $1,
                thompson_beta   = thompson_beta  + $2,
                priority_score  = (thompson_alpha + $1)::numeric
                                / (thompson_alpha + thompson_beta + $1 + $2),
                listings_found  = listings_found + $3,
                listings_new    = listings_new   + $3,
                last_crawled_at = NOW(),
                next_crawl_at   = NOW() + (recrawl_interval_s * INTERVAL '1 second'),
                updated_at      = NOW()
            WHERE id = $4
            """,
            alpha_inc, beta_inc, vehicles_found, row_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_due_rows(pool: Any, limit: int) -> list[Any]:
    """Select rows due for crawl and claim them (next_crawl_at → +1h) atomically."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT cf.id, cf.platform, cf.country, cf.make, cf.year,
                       cf.thompson_alpha, cf.thompson_beta,
                       COALESCE(dp.inventory_urls, '{}'::text[]) AS inventory_urls
                  FROM crawl_frontier cf
                  LEFT JOIN dealer_profile dp ON dp.domain = cf.platform
                 WHERE cf.next_crawl_at IS NULL
                    OR cf.next_crawl_at <= NOW()
                 ORDER BY cf.priority_score DESC
                 LIMIT $1
                 FOR UPDATE OF cf SKIP LOCKED
                """,
                limit,
            )
            if rows:
                ids = [r["id"] for r in rows]
                await conn.execute(
                    "UPDATE crawl_frontier"
                    "   SET next_crawl_at = NOW() + INTERVAL '1 hour'"
                    " WHERE id = ANY($1::bigint[])",
                    ids,
                )
            return list(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Per-row processing
# ─────────────────────────────────────────────────────────────────────────────

async def _process_row(
    pool: Any,
    rdb: Any,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    row: Any,
) -> None:
    row_id: int = row["id"]
    platform: str = row["platform"]
    country: str = row["country"]
    inv_urls: list[str] = list(row["inventory_urls"])

    if not inv_urls:
        # No inventory URLs discovered by classifier yet
        await _update_thompson(pool, row_id, 0)
        return

    async with sem:
        crawl = await _crawl_segment(client, inv_urls, platform)

    if crawl.vehicle_urls:
        await delta(
            pool, rdb,
            f"discovery:{platform}", country, platform,
            crawl.vehicle_urls,
        )

    await _update_thompson(pool, row_id, crawl.vehicles_found)
    log.info(
        "frontier id=%d platform=%s pages=%d vehicles=%d",
        row_id, platform, crawl.pages_crawled, crawl.vehicles_found,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = await make_pg()
    rdb = await make_redis()
    try:
        await ensure_schema(pool)
        rows = await _fetch_due_rows(pool, _BATCH)
        if not rows:
            log.info("No frontier rows due — exiting")
            return
        log.info(
            "Processing %d frontier rows (concurrency=%d)", len(rows), _CONCURRENCY
        )
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
            tasks = [_process_row(pool, rdb, client, sem, row) for row in rows]
            await asyncio.gather(*tasks, return_exceptions=True)
        log.info("DONE elapsed=%.1fs", time.monotonic() - t0)
    finally:
        await rdb.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
