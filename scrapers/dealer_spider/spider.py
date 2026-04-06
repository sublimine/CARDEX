"""
Dealer Web Spider — orchestrator for extracting inventory from dealer websites.

4-Vector Extraction Engine:
  Vector 1: JSON-LD (schema.org/Car) — instant, zero cost
  Vector 2: Sitemap vehicle URLs → JSON-LD on detail pages
  Vector 3: Playwright XHR/API interception — catches ALL SPAs
  Vector 4: Playwright iframe extraction — catches DMS embeds

Flow:
  1. Reads from stream:dealer_discovered (populated by DiscoveryOrchestrator)
  2. For each dealer with a website_url:
     a. Fetches homepage HTML via aiohttp (fast, cheap)
     b. Tries vectors 1-2 (pure HTTP, no browser)
     c. If vectors 1-2 yield nothing, escalates to Playwright (vectors 3-4)
     d. Listings are published to the standard pipeline via GatewayClient
     e. Dealer spider_status updated in PostgreSQL (DONE / FAILED / NO_INVENTORY)

Concurrency model:
  - SPIDER_CONCURRENCY workers (default 10) process dealers in parallel
  - Playwright limited to 3 concurrent pages (_PW_SEMAPHORE)
  - Bloom filter prevents re-crawling within TTL window (7 days)

Re-crawl strategy:
  - Dealers with spider_status=DONE are re-queued after 7 days
  - Dealers with spider_status=FAILED are retried after 24h (up to 3 attempts)
  - Dealers with NO_INVENTORY are checked weekly (website may add stock)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import AsyncGenerator
from urllib.parse import urljoin, urlparse

import aiohttp
import asyncpg
from redis.asyncio import from_url as redis_from_url

from scrapers.common.gateway_client import GatewayClient
from scrapers.common.models import RawListing
from scrapers.dealer_spider.detector import DMSDetector
from scrapers.dealer_spider.dms import (
    autobiz,
    autentia,
    incadea,
    motormanager,
    wp_car_manager,
)
from scrapers.dealer_spider.dms import generic_feed, schema_org, generic_html
from scrapers.dealer_spider.dms.schema_org import (
    _extract_jsonld_blocks,
    _is_vehicle,
    _vehicle_from_jsonld,
    _parse_sitemap_vehicle_urls,
)
from scrapers.dealer_spider.dms.generic_feed import _parse_json as _parse_vehicle_json

# Playwright import — graceful fallback if not installed
try:
    from scrapers.common.playwright_client import PlaywrightClient
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [spider] %(message)s",
    force=True,
)
log = logging.getLogger("spider")

_STREAM_IN  = "stream:dealer_discovered"
_CG_SPIDER  = "cg_dealer_spider"
_CONCURRENCY = int(os.environ.get("SPIDER_CONCURRENCY", "10"))
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)

# Playwright concurrency cap — 3 simultaneous browser pages max
_PW_SEMAPHORE: asyncio.Semaphore | None = None
_PW_MAX_CONCURRENT = 3
_PW_TIMEOUT = 30_000  # 30s per dealer

# Maps DMS platform string → extractor coroutine (used as fallback for known DMS)
_DMS_EXTRACTORS = {
    "autobiz":       autobiz.extract,
    "autentia":      autentia.extract,
    "incadea":       incadea.extract,
    "motormanager":  motormanager.extract,
    "wp_car_manager": wp_car_manager.extract,
    "dealer_inspire": generic_feed.extract,
    "dealersocket":   generic_feed.extract,
    "automanager":    generic_feed.extract,
    "generic_feed":   generic_feed.extract,
    "schema_org":     schema_org.extract,
    "generic_html":   generic_html.extract,
}

_HEADERS = {
    "User-Agent": (
        "CardexBot/1.0 (+https://cardex.eu/bot; scraping@cardex.eu) "
        "aiohttp/3.9 Python/3.12"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}

# Inventory page paths to try with Playwright
_INVENTORY_PATHS = [
    "/stock", "/inventory", "/vehicles", "/cars", "/used-cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion", "/gebrauchtwagen",
    "/tweedehands", "/occasions", "/gamas/ocasion", "/angebote",
    "/usados", "/coches-ocasion", "/autos", "/fleet",
]

# Iframe URL patterns that indicate inventory embeds
_IFRAME_VEHICLE_PATTERNS = re.compile(
    r"(stock|inventory|vehicle|autoscout|mobile\.de|modix|"
    r"autobiz|autentia|incadea|motormanager|car|fahrzeug|"
    r"voiture|coche|occasion|tweedehands)",
    re.IGNORECASE,
)


# ── HTTP helpers shared across workers ───────────────────────────────────────

class _HTTPHelper:
    """Thin async HTTP helper injected into DMS adapters."""

    def __init__(self, session: aiohttp.ClientSession):
        self._s = session

    async def get_json(self, url: str, **kwargs) -> dict | list:
        async with self._s.get(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def post_json(self, url: str, **kwargs) -> dict | list:
        async with self._s.post(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def get_text(self, url: str, **kwargs) -> str:
        async with self._s.get(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.text()

    async def head_ok(self, url: str) -> bool:
        try:
            async with self._s.head(
                url, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True,
            ) as r:
                return r.status < 400
        except Exception:
            return False


# ── False-positive filter (repair shops, parts stores, rental agencies) ──────

_NOT_DEALER_PATTERNS = [
    re.compile(r"\b(werkstatt|reparatur|autowerkstatt|kfz-werkstatt)\b", re.I),  # DE repair
    re.compile(r"\b(taller|reparación|mecánico)\b", re.I),  # ES repair
    re.compile(r"\b(atelier|réparation|garage de réparation)\b", re.I),  # FR repair
    re.compile(r"\b(car hire|autoverhuur|location de voiture|mietwagen)\b", re.I),  # rental
    re.compile(r"\b(auto parts|pièces auto|recambios|ersatzteile|onderdelen)\b", re.I),  # parts
    re.compile(r"\b(fahrschule|auto-école|autoescuela|rijschool)\b", re.I),  # driving school
]

_IS_DEALER_PATTERNS = [
    re.compile(r"\b(autohaus|händler|fahrzeuge|gebrauchtwagen|neuwagen)\b", re.I),  # DE
    re.compile(r"\b(concesionario|coches|vehículos|ocasión|seminuevo)\b", re.I),  # ES
    re.compile(r"\b(concessionnaire|véhicule|occasion|voiture)\b", re.I),  # FR
    re.compile(r"\b(dealer|showroom|inventory|stock|te koop)\b", re.I),  # NL/EN
    re.compile(r"\b(vente|verkauf|verkoop|vendita)\b", re.I),  # sales
]


def _is_likely_dealer(html: str) -> bool:
    """Returns True if page looks like a car dealer, False if repair/parts/rental."""
    not_dealer_score = sum(1 for p in _NOT_DEALER_PATTERNS if p.search(html))
    is_dealer_score = sum(1 for p in _IS_DEALER_PATTERNS if p.search(html))
    if not_dealer_score >= 2 and is_dealer_score == 0:
        return False
    return True


# ── Vector 1: JSON-LD extraction from pre-fetched HTML ──────────────────────

def _extract_jsonld_vehicles(
    html: str,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> list[RawListing]:
    """Extract vehicle listings from JSON-LD blocks in HTML. Zero network cost."""
    listings = []
    seen: set[str] = set()
    for obj in _extract_jsonld_blocks(html):
        if not _is_vehicle(obj):
            continue
        listing = _vehicle_from_jsonld(obj, dealer_id, dealer_name, base_url, country)
        if listing and listing.source_listing_id not in seen:
            seen.add(listing.source_listing_id)
            listings.append(listing)
    return listings


# ── Vector 2: Sitemap → vehicle detail pages → JSON-LD ──────────────────────

async def _extract_via_sitemap(
    http: _HTTPHelper,
    base_url: str,
    dealer_id: str,
    dealer_name: str,
    country: str,
) -> list[RawListing]:
    """Fetch sitemap.xml, find vehicle URLs, scrape JSON-LD from detail pages."""
    base = base_url.rstrip("/")
    listings: list[RawListing] = []
    seen: set[str] = set()

    try:
        sitemap_text = await http.get_text(base + "/sitemap.xml")
    except Exception:
        return []

    vehicle_urls = _parse_sitemap_vehicle_urls(sitemap_text, base)
    if not vehicle_urls:
        return []

    # Cap at 200 detail pages to avoid hammering small sites
    for url in vehicle_urls[:200]:
        try:
            html = await http.get_text(url)
            for obj in _extract_jsonld_blocks(html):
                if not _is_vehicle(obj):
                    continue
                listing = _vehicle_from_jsonld(obj, dealer_id, dealer_name, base, country)
                if listing and listing.source_listing_id not in seen:
                    seen.add(listing.source_listing_id)
                    listings.append(listing)
        except Exception:
            continue

    return listings


# ── Vector 3+4: Playwright XHR interception + iframe extraction ──────────────

def _find_vehicles_in_json(
    data,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
    depth: int = 0,
) -> list[RawListing]:
    """
    Recursively search intercepted JSON payloads for vehicle-like objects.
    Handles both flat arrays and nested structures (data.results, data.vehicles, etc.).
    """
    if depth > 5:
        return []

    listings: list[RawListing] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                listing = _parse_vehicle_json(item, dealer_id, dealer_name, base_url, country)
                if listing:
                    listings.append(listing)
                elif depth < 5:
                    # Recurse into nested structures
                    listings.extend(
                        _find_vehicles_in_json(item, dealer_id, dealer_name, base_url, country, depth + 1)
                    )
        return listings

    if isinstance(data, dict):
        # Try parsing the dict itself as a vehicle
        listing = _parse_vehicle_json(data, dealer_id, dealer_name, base_url, country)
        if listing:
            return [listing]

        # Search known wrapper keys for arrays of vehicles
        _WRAPPER_KEYS = [
            "vehicles", "stock", "cars", "inventory", "items", "results",
            "data", "listings", "records", "content", "hits", "ads",
            "fahrzeuge", "voitures", "coches", "autos", "occasions",
            "searchResults", "vehicleList", "stockList", "response",
        ]
        for key in _WRAPPER_KEYS:
            val = data.get(key)
            if isinstance(val, list) and len(val) > 0:
                nested = _find_vehicles_in_json(val, dealer_id, dealer_name, base_url, country, depth + 1)
                if nested:
                    return nested
            elif isinstance(val, dict) and depth < 5:
                nested = _find_vehicles_in_json(val, dealer_id, dealer_name, base_url, country, depth + 1)
                if nested:
                    return nested

    return listings


async def _extract_with_playwright(
    base_url: str,
    dealer_id: str,
    dealer_name: str,
    country: str,
    homepage_html: str,
) -> list[RawListing]:
    """
    Vectors 3+4: Open dealer site in Playwright, intercept XHR JSON responses,
    extract iframes, parse everything for vehicle data.
    """
    global _PW_SEMAPHORE
    if not _HAS_PLAYWRIGHT:
        log.debug("spider: Playwright not available, skipping vectors 3-4 for %s", dealer_name)
        return []

    if _PW_SEMAPHORE is None:
        _PW_SEMAPHORE = asyncio.Semaphore(_PW_MAX_CONCURRENT)

    async with _PW_SEMAPHORE:
        return await _run_playwright_extraction(base_url, dealer_id, dealer_name, country, homepage_html)


async def _run_playwright_extraction(
    base_url: str,
    dealer_id: str,
    dealer_name: str,
    country: str,
    homepage_html: str,
) -> list[RawListing]:
    """Core Playwright extraction logic — runs under semaphore."""
    base = base_url.rstrip("/")
    all_listings: list[RawListing] = []
    seen_ids: set[str] = set()

    def _dedupe(listings: list[RawListing]) -> list[RawListing]:
        unique = []
        for l in listings:
            if l.source_listing_id not in seen_ids:
                seen_ids.add(l.source_listing_id)
                unique.append(l)
        return unique

    # Determine which inventory URLs to try
    # First, check homepage HTML for inventory links
    inventory_urls: list[str] = []
    inventory_urls.extend(DMSDetector.find_inventory_links(base, homepage_html))

    # Add standard inventory paths
    for path in _INVENTORY_PATHS:
        candidate = base + path
        if candidate not in inventory_urls:
            inventory_urls.append(candidate)

    # Always try the homepage itself too (some SPAs load inventory on /)
    if base not in inventory_urls:
        inventory_urls.insert(0, base)

    try:
        async with PlaywrightClient(headless=True, country=country) as pw:
            # Try each inventory URL until we find vehicles
            for url in inventory_urls[:6]:  # Cap at 6 URLs to stay within timeout
                try:
                    html, intercepted_json, iframe_srcs = await pw.get_page_with_interception(
                        url, timeout=_PW_TIMEOUT,
                    )
                except Exception as exc:
                    log.debug("spider: Playwright failed for %s: %s", url, exc)
                    continue

                # Vector 3: Parse intercepted XHR JSON payloads
                for payload in intercepted_json:
                    vehicles = _find_vehicles_in_json(
                        payload, dealer_id, dealer_name, base, country,
                    )
                    all_listings.extend(_dedupe(vehicles))

                # Also check if the rendered HTML now has JSON-LD (SPA may inject it)
                jsonld_vehicles = _extract_jsonld_vehicles(html, dealer_id, dealer_name, base, country)
                all_listings.extend(_dedupe(jsonld_vehicles))

                # Vector 4: Process vehicle-related iframes
                vehicle_iframes = [
                    src for src in iframe_srcs
                    if _IFRAME_VEHICLE_PATTERNS.search(src)
                ]
                for iframe_src in vehicle_iframes[:3]:  # Cap at 3 iframes
                    # Resolve relative iframe URLs
                    if not iframe_src.startswith("http"):
                        iframe_src = urljoin(base + "/", iframe_src)
                    try:
                        iframe_html, iframe_json, _ = await pw.get_page_with_interception(
                            iframe_src, timeout=_PW_TIMEOUT,
                        )
                        # Parse iframe XHR payloads
                        for payload in iframe_json:
                            vehicles = _find_vehicles_in_json(
                                payload, dealer_id, dealer_name, base, country,
                            )
                            all_listings.extend(_dedupe(vehicles))
                        # Parse iframe HTML for JSON-LD
                        jsonld_vehicles = _extract_jsonld_vehicles(
                            iframe_html, dealer_id, dealer_name, base, country,
                        )
                        all_listings.extend(_dedupe(jsonld_vehicles))
                    except Exception as exc:
                        log.debug("spider: iframe extraction failed %s: %s", iframe_src, exc)
                        continue

                # If we found vehicles, stop trying more URLs
                if all_listings:
                    break

    except Exception as exc:
        log.warning("spider: Playwright session failed for %s: %s", dealer_name, exc)

    return all_listings


# ── Spider worker ─────────────────────────────────────────────────────────────

async def _process_dealer(
    msg_id: str,
    fields: dict,
    session: aiohttp.ClientSession,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """
    Process a single dealer using the 4-vector extraction engine.
    Tries vectors in order, stops at the first one that yields vehicles.
    Falls back to legacy DMS-specific extractors for known platforms.
    """
    dealer_id = fields.get("dealer_id", "")
    name      = fields.get("name", "unknown")
    country   = fields.get("country", "")
    website   = fields.get("website", "").strip()

    if not website or not website.startswith("http"):
        print(f"[spider] SKIP {name} ({country}): no website", flush=True)
        await _update_spider_status(pg, dealer_id, name, country, "NO_INVENTORY", "no_website")
        return

    print(f"[spider] PROCESSING {name} ({country}): {website}", flush=True)

    # Bloom: skip if crawled recently
    bloom_key = f"dealer:crawled:{dealer_id}"
    if await rdb.exists(bloom_key):
        log.debug("spider: skip %s (bloom hit)", name)
        return

    http = _HTTPHelper(session)

    # ── Step 1: Fetch homepage with aiohttp (fast, cheap) ────────────────
    try:
        async with session.get(
            website, timeout=_REQUEST_TIMEOUT, headers=_HEADERS, allow_redirects=True,
        ) as resp:
            if resp.status >= 400:
                log.warning("spider: %s homepage HTTP %d", name, resp.status)
                await _update_spider_status(pg, dealer_id, name, country, "FAILED", f"http_{resp.status}")
                return
            html = await resp.text(errors="replace")
            base_url = str(resp.url).rstrip("/")
    except Exception as exc:
        log.warning("spider: %s homepage fetch failed: %s", name, exc)
        await _update_spider_status(pg, dealer_id, name, country, "FAILED", str(exc)[:120])
        return

    # Filter false positives (repair shops, parts stores, rental agencies)
    if not _is_likely_dealer(html):
        log.info("spider: %s filtered as non-dealer (repair/parts/rental)", name)
        await _update_spider_status(pg, dealer_id, name, country, "NO_INVENTORY", "false_positive")
        return

    listing_count = 0
    error_count   = 0
    vector_used   = "none"

    # ── VECTOR 1: JSON-LD extraction (instant, zero cost) ────────────────
    listings = _extract_jsonld_vehicles(html, dealer_id, name, base_url, country)
    if listings:
        vector_used = "jsonld"
        log.info("spider: %s → Vector 1 (JSON-LD): %d vehicles", name, len(listings))

    # ── VECTOR 2: Sitemap → vehicle detail pages → JSON-LD ──────────────
    if not listings:
        try:
            listings = await _extract_via_sitemap(http, base_url, dealer_id, name, country)
            if listings:
                vector_used = "sitemap"
                log.info("spider: %s → Vector 2 (sitemap): %d vehicles", name, len(listings))
        except Exception as exc:
            log.debug("spider: %s sitemap extraction failed: %s", name, exc)

    # ── LEGACY: Try known DMS extractors if detected ─────────────────────
    # This preserves existing working extractors for known platforms
    if not listings:
        detector = DMSDetector(http)
        platform, feed_url = await detector.detect(base_url, html)
        if platform not in ("generic_html", "schema_org"):
            # Known DMS detected — use its specific extractor
            extractor = _DMS_EXTRACTORS.get(platform)
            if extractor:
                try:
                    collected: list[RawListing] = []
                    async for listing in extractor(
                        http=http,
                        dealer_id=dealer_id,
                        dealer_name=name,
                        base_url=feed_url or base_url,
                        country=country,
                    ):
                        collected.append(listing)
                    if collected:
                        listings = collected
                        vector_used = f"dms:{platform}"
                        log.info("spider: %s → Legacy DMS (%s): %d vehicles", name, platform, len(listings))
                except Exception as exc:
                    log.debug("spider: %s DMS extractor %s failed: %s", name, platform, exc)

    # ── VECTORS 3+4: Playwright XHR interception + iframe extraction ─────
    if not listings:
        try:
            listings = await _extract_with_playwright(
                base_url, dealer_id, name, country, html,
            )
            if listings:
                vector_used = "playwright"
                log.info("spider: %s → Vectors 3+4 (Playwright): %d vehicles", name, len(listings))
        except Exception as exc:
            log.warning("spider: %s Playwright extraction failed: %s", name, exc)

    # ── Publish all extracted listings ────────────────────────────────────
    if listings:
        for listing in listings:
            try:
                await gateway.ingest(listing)
                listing_count += 1
                if listing_count <= 3:
                    print(
                        f"[spider] VEHICLE {name}: {listing.make} {listing.model} "
                        f"{listing.year} EUR{listing.price_raw}",
                        flush=True,
                    )
            except Exception as exc:
                error_count += 1
                if error_count <= 3:
                    print(f"[spider] INGEST_ERR {name}: {exc}", flush=True)

    print(
        f"[spider] RESULT {name} ({country}): vector={vector_used} "
        f"listings={listing_count} errors={error_count}",
        flush=True,
    )

    # Update dealer record
    status = "DONE" if listing_count > 0 else "NO_INVENTORY"
    await _update_spider_status(pg, dealer_id, name, country, status, vector_used, listing_count)

    # Mark as crawled in bloom (7-day TTL)
    await rdb.set(bloom_key, "1", ex=7 * 86400)

    log.info(
        "spider: %s done — vector=%s listings=%d errors=%d",
        name, vector_used, listing_count, error_count,
    )


async def _update_spider_status(
    pg: asyncpg.Pool,
    dealer_id: str,
    name: str,
    country: str,
    status: str,
    dms_or_reason: str = "",
    listing_count: int = 0,
) -> None:
    try:
        await pg.execute("""
            UPDATE dealers
            SET spider_status       = $1,
                spider_last_run     = now(),
                spider_dms          = $2,
                spider_listing_count = $3,
                updated_at          = now()
            WHERE name = $4 AND country = $5
        """, status, dms_or_reason[:64], listing_count, name, country)
    except Exception as exc:
        log.warning("spider: db update failed dealer=%s: %s", name, exc)


# ── Consumer loop ─────────────────────────────────────────────────────────────

async def _consumer(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """Long-running consumer that reads from the Redis stream."""
    conn_headers = {
        **_HEADERS,
        "Connection": "keep-alive",
    }
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        headers=conn_headers,
        connector=connector,
        trust_env=True,
    ) as session:
        last_id = ">"   # read only new messages
        while True:
            try:
                entries = await rdb.xreadgroup(
                    groupname=_CG_SPIDER,
                    consumername=f"spider-worker-{worker_id}",
                    streams={_STREAM_IN: last_id},
                    count=1,
                    block=5000,   # 5s block
                )
            except Exception as exc:
                log.warning("spider worker %d: xreadgroup error: %s", worker_id, exc)
                await asyncio.sleep(2)
                continue

            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    async with semaphore:
                        try:
                            await asyncio.wait_for(
                                _process_dealer(
                                    msg_id, fields, session, pg, rdb, gateway,
                                ),
                                timeout=90.0,  # 90s max per dealer
                            )
                        except asyncio.TimeoutError:
                            name = fields.get("name", "?")
                            print(f"[spider] TIMEOUT {name} (>90s)", flush=True)
                        except Exception as exc:
                            log.error("spider worker %d: unhandled error: %s", worker_id, exc)
                        finally:
                            # Always ACK — failures are tracked in DB, not re-queued
                            try:
                                await rdb.xack(_STREAM_IN, _CG_SPIDER, msg_id)
                            except Exception:
                                pass


# ── Bootstrap ─────────────────────────────────────────────────────────────────

async def _ensure_consumer_group(rdb) -> None:
    """Create the consumer group if it doesn't exist."""
    try:
        await rdb.xgroup_create(_STREAM_IN, _CG_SPIDER, id="0", mkstream=True)
        log.info("spider: created consumer group %s", _CG_SPIDER)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            pass  # already exists
        else:
            log.warning("spider: xgroup_create warning: %s", exc)


async def run() -> None:
    """Entry point for run_scraper.py target 'dealer_spider'."""
    import signal
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [spider] %(message)s",
    )

    rdb = redis_from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    pg  = await asyncpg.create_pool(
        os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"),
        min_size=2, max_size=8,
    )
    gateway = GatewayClient()

    await _ensure_consumer_group(rdb)

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    stop_event = asyncio.Event()

    def _handle_signal(*_):
        log.info("spider: shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT,  _handle_signal)
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)

    log.info("spider: starting %d workers (concurrency=%d)", _CONCURRENCY, _CONCURRENCY)

    workers = [
        asyncio.create_task(_consumer(i, semaphore, pg, rdb, gateway))
        for i in range(_CONCURRENCY)
    ]

    await stop_event.wait()

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    await pg.close()
    await rdb.aclose()
    await gateway.close()
    log.info("spider: shutdown complete")
