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
     a. Fetches homepage HTML via StealthClient (curl_cffi TLS impersonation)
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

import asyncpg
from redis.asyncio import from_url as redis_from_url
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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

# Stealth HTTP layer — curl_cffi with TLS impersonation
from scrapers.dealer_spider.stealth_http import (
    StealthClient, StealthHTTPHelper, StealthBlockError,
    detect_waf_type, is_challenge_page,
    _HAS_PROXIES,
)

# Type alias for function signatures that accept the HTTP helper
_HTTPHelper = StealthHTTPHelper

# Stealth Playwright — graceful fallback if not installed
try:
    import playwright  # noqa: F401
    from scrapers.dealer_spider.stealth_browser import (
        StealthBrowser, CaptchaUnavailableError,
    )
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False
    CaptchaUnavailableError = None  # type: ignore[misc, assignment]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [spider] %(message)s",
    force=True,
)
log = logging.getLogger("spider")

_STREAM_IN  = "stream:dealer_discovered"
_CG_SPIDER  = "cg_dealer_spider"
_CONCURRENCY = int(os.environ.get("SPIDER_CONCURRENCY", "10"))

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
        # Handle ItemList wrapping individual Vehicle entries
        if isinstance(obj, dict) and obj.get("@type") == "ItemList":
            for element in obj.get("itemListElement", []):
                item = element if isinstance(element, dict) else {}
                # ListItem wraps the actual item
                if item.get("@type") == "ListItem":
                    item = item.get("item", item)
                if _is_vehicle(item):
                    listing = _vehicle_from_jsonld(item, dealer_id, dealer_name, base_url, country)
                    if listing and listing.source_listing_id not in seen:
                        seen.add(listing.source_listing_id)
                        listings.append(listing)
            continue
        if not _is_vehicle(obj):
            continue
        listing = _vehicle_from_jsonld(obj, dealer_id, dealer_name, base_url, country)
        if listing and listing.source_listing_id not in seen:
            seen.add(listing.source_listing_id)
            listings.append(listing)
    return listings


# ── Dynamic Pagination Engine ──────────────────────────────────────────────────
#
# Three pagination strategies tried in order of confidence:
#   1. KNOWN_TOTAL — JSON-LD AggregateOffer.offerCount / XHR total_pages → compute page range
#   2. DOM_SIGNAL  — <link rel="next">, pagination buttons, href with page=N
#   3. PARAM_PROBE — detected ?page= param on first hit → increment until empty
#
# Exhaustion signals (any one stops the crawl):
#   - HTTP 404/410
#   - Empty vehicle list on a page
#   - 3 consecutive pages with 100% duplicate IDs
#   - Reached computed max_pages (from KNOWN_TOTAL) or hard cap (2000)

_PAGE_PARAM_NAMES = ("page", "p", "pagina", "seite", "pag", "offset", "start", "skip")
_MAX_PAGES_HARD_CAP = 2000


def _estimate_total_pages(html: str, items_per_page: int) -> int | None:
    """
    Extract total item count from JSON-LD AggregateOffer or Product metadata.
    Returns estimated total pages, or None if no signal found.
    """
    if items_per_page <= 0:
        return None
    for obj in _extract_jsonld_blocks(html):
        # AggregateOffer on a Product or standalone
        offers = None
        if isinstance(obj, dict):
            if obj.get("@type") == "Product":
                offers = obj.get("offers") or obj.get("Offers")
            elif obj.get("@type") in ("AggregateOffer", "AggregateRating"):
                offers = obj
        if isinstance(offers, dict) and offers.get("@type") == "AggregateOffer":
            count = offers.get("offerCount")
            if count is not None:
                try:
                    total = int(count)
                    pages = (total + items_per_page - 1) // items_per_page
                    return min(pages, _MAX_PAGES_HARD_CAP)
                except (ValueError, TypeError):
                    pass
    return None


def _detect_page_param(url: str) -> str | None:
    """If the URL already contains a known page parameter, return its name."""
    params = parse_qs(urlparse(url).query)
    for key in _PAGE_PARAM_NAMES:
        if key in params:
            return key
    return None


def _build_page_url(base_page_url: str, page_param: str, page_num: int) -> str:
    """Build URL for a specific page number using the detected parameter."""
    parsed = urlparse(base_page_url)
    params = parse_qs(parsed.query)
    params[page_param] = [str(page_num)]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _find_next_url_in_html(html: str, current_page_num: int, base_netloc: str) -> str | None:
    """
    Parse DOM for pagination signals: rel=next, page links, next buttons.
    Returns absolute URL or None.
    """
    def _abs(href: str) -> str | None:
        if not href:
            return None
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"https://{base_netloc}{href}"
        return None

    # 1. <link rel="next"> or <a rel="next">
    for pattern in [
        r'<(?:a|link)[^>]+rel=["\']next["\'][^>]+href=["\']([^"\']+)["\']',
        r'<(?:a|link)[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']next["\']',
    ]:
        m = re.search(pattern, html, re.I)
        if m:
            result = _abs(m.group(1))
            if result:
                return result

    # 2. Explicit href with page=<next_page_num>
    next_num = current_page_num + 1
    m = re.search(
        r'href=["\']([^"\']*[?&]page=' + str(next_num) + r'(?:&[^"\']*)?)["\']',
        html, re.I,
    )
    if m:
        result = _abs(m.group(1))
        if result:
            return result

    # 3. Multilingual "next" button text
    m = re.search(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*'
        r'(?:next|siguiente|suivant|weiter|volgende|nächste|próximo|avanti|'
        r'›|»|→|&#8250;|&#187;|&#8594;)\s*</a>',
        html, re.I,
    )
    if m:
        result = _abs(m.group(1))
        if result:
            return result

    return None


async def _paginate_jsonld(
    stealth: StealthClient,
    tier: int,
    first_page_url: str,
    first_page_html: str,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> tuple[list[RawListing], int]:
    """
    Dynamic Pagination Engine — uses StealthClient (curl_cffi) for every page.
    Same TLS fingerprint from page 1 to page 661. Pure curl_cffi.
    Returns (all_listings, pages_crawled).
    """
    all_listings: list[RawListing] = []
    seen_ids: set[str] = set()

    # ── Process first page ──────────────────────────────────────────────
    page_listings = _extract_jsonld_vehicles(first_page_html, dealer_id, dealer_name, base_url, country)
    for listing in page_listings:
        if listing.source_listing_id not in seen_ids:
            seen_ids.add(listing.source_listing_id)
            all_listings.append(listing)

    if not page_listings:
        return all_listings, 1

    items_per_page = len(page_listings)
    pages_crawled = 1
    consecutive_dup_pages = 0
    parsed_base = urlparse(first_page_url)

    # ── Determine pagination strategy ───────────────────────────────────

    # Strategy A: Compute total from AggregateOffer metadata
    estimated_pages = _estimate_total_pages(first_page_html, items_per_page)

    # Strategy B: Detect existing page param in URL
    page_param = _detect_page_param(first_page_url)

    # Strategy C: Probe ?page=2 through stealth
    if not page_param:
        probe_url = _build_page_url(first_page_url, "page", 2)
        try:
            status, probe_html, _, _ = await stealth.get(probe_url, tier=tier)
            if status < 400:
                probe_listings = _extract_jsonld_vehicles(
                    probe_html, dealer_id, dealer_name, base_url, country,
                )
                if probe_listings:
                    probe_ids = {l.source_listing_id for l in probe_listings}
                    if not probe_ids.issubset(seen_ids):
                        page_param = "page"
                        if estimated_pages is None:
                            estimated_pages = _estimate_total_pages(probe_html, items_per_page)
                        for listing in probe_listings:
                            if listing.source_listing_id not in seen_ids:
                                seen_ids.add(listing.source_listing_id)
                                all_listings.append(listing)
                        pages_crawled += 1
        except Exception:
            pass

    # DOM-based fallback
    if not page_param:
        dom_next = _find_next_url_in_html(first_page_html, 1, parsed_base.netloc)
        if not dom_next:
            return all_listings, pages_crawled

    # ── Compute max pages ───────────────────────────────────────────────
    max_pages = min(estimated_pages, _MAX_PAGES_HARD_CAP) if estimated_pages else _MAX_PAGES_HARD_CAP
    start_page = pages_crawled + 1
    last_html = first_page_html

    log.info(
        "spider: %s pagination: strategy=%s, estimated_pages=%s, items_per_page=%d",
        dealer_name,
        f"param:{page_param}" if page_param else "dom",
        estimated_pages or "unknown",
        items_per_page,
    )

    # ── Page loop — every request through StealthClient ─────────────────
    for page_num in range(start_page, max_pages + 1):
        if page_param:
            next_url = _build_page_url(first_page_url, page_param, page_num)
        else:
            next_url = _find_next_url_in_html(last_html, page_num - 1, parsed_base.netloc)
            if not next_url:
                break

        try:
            status, html, _, _ = await stealth.get(next_url, tier=tier)
            if status in (404, 410):
                break
            if status >= 400:
                break
        except StealthBlockError:
            break  # WAF kicked in mid-pagination — stop gracefully
        except Exception:
            break

        page_listings = _extract_jsonld_vehicles(html, dealer_id, dealer_name, base_url, country)
        if not page_listings:
            break

        new_count = 0
        for listing in page_listings:
            if listing.source_listing_id not in seen_ids:
                seen_ids.add(listing.source_listing_id)
                all_listings.append(listing)
                new_count += 1

        pages_crawled += 1

        if new_count == 0:
            consecutive_dup_pages += 1
            if consecutive_dup_pages >= 3:
                break
        else:
            consecutive_dup_pages = 0

        last_html = html

        if pages_crawled % 50 == 0:
            print(
                f"[SWARM] {dealer_name}: pagination progress — "
                f"page {pages_crawled}/{max_pages}, {len(all_listings)} vehicles so far",
                flush=True,
            )

    return all_listings, pages_crawled


# Inventory paths for Vector 1 probing (matches schema_org.py _PROBE_PATHS)
_JSONLD_PROBE_PATHS = [
    "/stock", "/inventory", "/vehicles", "/cars", "/used-cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion", "/gebrauchtwagen",
    "/tweedehands", "/occasions", "/coches-segunda-mano", "/gamas/ocasion",
]


def _normalize_source_url(url: str | None, base_url: str) -> str | None:
    """
    Normalize a source URL to absolute form.
    Handles: relative paths (/vehiculo/123), protocol-relative (//cdn.example.com/...),
    and already-absolute URLs.
    Returns None if the URL is unusable.
    """
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        # Relative path — join with base
        return urljoin(base_url.rstrip("/") + "/", url)
    # Bare relative path (no leading /)
    if url and not url.startswith("#") and not url.startswith("javascript:"):
        return urljoin(base_url.rstrip("/") + "/", url)
    return None


def _is_root_domain_url(url: str) -> bool:
    """Return True if url is just a domain root with no meaningful path."""
    try:
        parsed = urlparse(url)
        return parsed.path.rstrip("/") == ""
    except Exception:
        return True


def _is_valid_listing(listing: RawListing) -> bool:
    """Reject garbage before it touches the pipeline."""
    if not listing.make or not listing.model:
        return False
    if listing.year and (listing.year < 1920 or listing.year > 2027):
        return False
    if listing.price_raw is not None and (listing.price_raw < 500 or listing.price_raw > 5_000_000):
        return False
    # CRITICAL: source_url must be a direct link to the listing, not a root domain
    if not listing.source_url or _is_root_domain_url(listing.source_url):
        return False
    return True


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
                    # Override source_url with the actual detail page URL we fetched
                    listing.source_url = url
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




# ── Spider worker ─────────────────────────────────────────────────────────────

async def _process_dealer(
    msg_id: str,
    fields: dict,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """
    Process a single dealer using the 4-vector extraction engine
    with stealth HTTP (TLS impersonation) and automatic proxy tier escalation.
    """
    dealer_id = fields.get("dealer_id", "")
    name      = fields.get("name", "unknown")
    country   = fields.get("country", "")
    website   = fields.get("website", "").strip()
    proxy_tier = int(fields.get("proxy_tier", "0"))
    is_whale   = fields.get("is_whale", "false") == "true"

    if not website or not website.startswith("http"):
        print(f"[SWARM] {name}: 0 vehicles extracted (no_website, 0 pages). PG insert rate: 0/sec", flush=True)
        await _update_spider_status(pg, dealer_id, name, country, "NO_INVENTORY", "no_website")
        return

    t0 = time.monotonic()
    pages_crawled = 0
    print(f"[SWARM] {name} ({country}) T{proxy_tier}: crawling {website}", flush=True)

    # Bloom: skip if crawled recently
    bloom_key = f"dealer:crawled:{dealer_id}"
    if await rdb.exists(bloom_key):
        log.debug("spider: skip %s (bloom hit)", name)
        return

    # ── Step 1: Fetch homepage with StealthClient ────────────────────────
    current_tier = proxy_tier
    html = None
    base_url = website.rstrip("/")
    waf_detected = "none"

    async with StealthClient(rdb, country=country) as stealth:
        # Determine max tier to attempt — if no proxies configured, only try T0
        max_tier = 3 if _HAS_PROXIES else 1

        for attempt_tier in range(current_tier, max_tier):
            try:
                status, html, resp_headers, waf_detected = await stealth.get(
                    website, tier=attempt_tier,
                )
                if status in (403, 429) and not _HAS_PROXIES:
                    # T0 direct IP hit WAF — immediate retreat, no retry
                    waf_detected = detect_waf_type(
                        {k.lower(): v for k, v in resp_headers.items()}
                    ) if resp_headers else "http_block"
                    log.info("spider: %s HTTP %d (T0 no proxy) — marking PENDING_PROXY", name, status)
                    await _update_dealer_waf(pg, dealer_id, name, country, 0, waf_detected)
                    await _update_spider_status(pg, dealer_id, name, country, "PENDING_PROXY", f"waf:{waf_detected}")
                    print(f"[SWARM] {name}: PENDING_PROXY (HTTP {status}, {waf_detected})", flush=True)
                    return
                if status >= 400:
                    log.warning("spider: %s homepage HTTP %d (T%d)", name, status, attempt_tier)
                    continue
                current_tier = attempt_tier
                break
            except StealthBlockError as e:
                waf_detected = e.waf_type
                if not _HAS_PROXIES:
                    # No proxies — don't escalate, mark for later
                    log.info("spider: %s blocked by %s (T0 no proxy) — PENDING_PROXY", name, e.waf_type)
                    await _update_dealer_waf(pg, dealer_id, name, country, 0, waf_detected)
                    await _update_spider_status(pg, dealer_id, name, country, "PENDING_PROXY", f"waf:{waf_detected}")
                    print(f"[SWARM] {name}: PENDING_PROXY ({waf_detected})", flush=True)
                    return
                log.info("spider: %s blocked by %s (T%d), escalating", name, e.waf_type, attempt_tier)
                continue
            except Exception as exc:
                log.warning("spider: %s homepage fetch failed (T%d): %s", name, attempt_tier, exc)
                continue

        if not html:
            await _update_dealer_waf(pg, dealer_id, name, country, current_tier, waf_detected)
            await _update_spider_status(pg, dealer_id, name, country, "FAILED", f"waf:{waf_detected}")
            print(f"[SWARM] {name}: BLOCKED by {waf_detected} (all tiers failed)", flush=True)
            return

        # Persist successful tier for future crawls
        if current_tier != proxy_tier:
            await _update_dealer_waf(pg, dealer_id, name, country, current_tier, waf_detected)

        # Filter false positives
        if not _is_likely_dealer(html):
            await _update_spider_status(pg, dealer_id, name, country, "NO_INVENTORY", "false_positive")
            return

        http = StealthHTTPHelper(stealth, tier=current_tier)
        listing_count = 0
        error_count   = 0
        vector_used   = "none"

        # ── VECTOR 1: JSON-LD extraction with pagination ─────────────────
        homepage_vehicles = _extract_jsonld_vehicles(html, dealer_id, name, base_url, country)
        if homepage_vehicles:
            listings, pages_crawled = await _paginate_jsonld(stealth, current_tier, website, html, dealer_id, name, base_url, country)
            vector_used = "jsonld"
        else:
            listings = []
            # Probe inventory paths in parallel batches

            async def _probe_one(path: str) -> tuple[str, str, list] | None:
                url = base_url + path
                try:
                    _st, text, _h, _w = await stealth.get(url, tier=current_tier)
                    vehs = _extract_jsonld_vehicles(text, dealer_id, name, base_url, country)
                    if vehs:
                        return (url, text, vehs)
                except Exception:
                    pass
                return None

            for i in range(0, len(_JSONLD_PROBE_PATHS), 4):
                batch = _JSONLD_PROBE_PATHS[i:i+4]
                results = await asyncio.gather(*[_probe_one(p) for p in batch])
                for result in results:
                    if result:
                        probe_url, probe_html, _ = result
                        listings, pages_crawled = await _paginate_jsonld(
                            stealth, current_tier, probe_url, probe_html, dealer_id, name, base_url, country,
                        )
                        vector_used = "jsonld"
                        break
                if listings:
                    break

        # ── VECTOR 2: Sitemap → vehicle detail pages → JSON-LD ──────────
        if not listings:
            try:
                listings = await _extract_via_sitemap(http, base_url, dealer_id, name, country)
                if listings:
                    vector_used = "sitemap"
            except Exception:
                pass

        # ── LEGACY: Known DMS extractors ─────────────────────────────────
        if not listings:
            detector = DMSDetector(http)
            platform, feed_url = await detector.detect(base_url, html)
            if platform not in ("generic_html", "schema_org"):
                extractor = _DMS_EXTRACTORS.get(platform)
                if extractor:
                    try:
                        collected: list[RawListing] = []
                        async for listing in extractor(
                            http=http, dealer_id=dealer_id, dealer_name=name,
                            base_url=feed_url or base_url, country=country,
                        ):
                            collected.append(listing)
                        if collected:
                            listings = collected
                            vector_used = f"dms:{platform}"
                    except Exception:
                        pass

    # ── VECTORS 3+4: Stealth Playwright — targeted XHR interception ──────
    # Active SPA extraction: opens stealth browser, intercepts internal API
    # calls (/api/, /vehicles, /graphql, etc.), grabs JSON at network layer.
    # If CAPTCHA blocks us and we can't solve → mark WAF_BLOCKED_NO_CAPTCHA, move on.
    if not listings and _HAS_PLAYWRIGHT:
        if _PW_SEMAPHORE is None:
            _PW_SEMAPHORE = asyncio.Semaphore(_PW_MAX_CONCURRENT)

        try:
            async with _PW_SEMAPHORE:
                async with StealthBrowser(
                    country=country, proxy_tier=current_tier, headless=True,
                ) as browser:
                    pw_json, pw_html, pw_iframes = await browser.extract_spa(
                        base_url=website,
                        is_whale=is_whale,
                        timeout=_PW_TIMEOUT,
                    )

                    # Vector 3: Parse intercepted XHR API responses
                    seen_pw: set[str] = set()
                    for payload in pw_json:
                        vehicles = _find_vehicles_in_json(
                            payload, dealer_id, name, base_url, country,
                        )
                        for v in vehicles:
                            if v.source_listing_id not in seen_pw:
                                seen_pw.add(v.source_listing_id)
                                listings.append(v)

                    # Also check rendered HTML for JSON-LD (SPAs may inject after render)
                    if pw_html:
                        jsonld_vehicles = _extract_jsonld_vehicles(
                            pw_html, dealer_id, name, base_url, country,
                        )
                        for v in jsonld_vehicles:
                            if v.source_listing_id not in seen_pw:
                                seen_pw.add(v.source_listing_id)
                                listings.append(v)

                    # Vector 4: Vehicle-related iframes
                    vehicle_iframes = [
                        src for src in pw_iframes
                        if _IFRAME_VEHICLE_PATTERNS.search(src)
                    ]
                    for iframe_src in vehicle_iframes[:3]:
                        if not iframe_src.startswith("http"):
                            iframe_src = urljoin(base_url + "/", iframe_src)
                        try:
                            iframe_html, iframe_json, _ = await browser.extract(
                                iframe_src, timeout=_PW_TIMEOUT,
                            )
                            for payload in iframe_json:
                                vehicles = _find_vehicles_in_json(
                                    payload, dealer_id, name, base_url, country,
                                )
                                for v in vehicles:
                                    if v.source_listing_id not in seen_pw:
                                        seen_pw.add(v.source_listing_id)
                                        listings.append(v)
                        except Exception:
                            continue

                    if listings:
                        vector_used = "playwright_xhr"

        except CaptchaUnavailableError as cap_err:
            log.warning("spider: %s CAPTCHA blocked — %s", name, cap_err.reason)
            await _update_dealer_waf(pg, dealer_id, name, country, current_tier, cap_err.waf_type)
            await _update_spider_status(
                pg, dealer_id, name, country,
                "WAF_BLOCKED_NO_CAPTCHA",
                f"captcha:{cap_err.reason}",
            )
            print(
                f"[SWARM] {name}: WAF_BLOCKED_NO_CAPTCHA — {cap_err.reason}. "
                f"Skipping to next dealer.",
                flush=True,
            )
            # Mark bloom so we don't retry immediately (24h cooldown for captcha blocks)
            await rdb.set(bloom_key, "1", ex=24 * 3600)
            return

        except Exception as exc:
            log.warning("spider: %s Playwright failed: %s", name, exc)

    # ── Normalize URLs + Publish all extracted listings ──────────────────
    if listings:
        for listing in listings:
            # URL normalization: resolve relative URLs against dealer base
            listing.source_url = _normalize_source_url(listing.source_url, base_url) or ""
            if not _is_valid_listing(listing):
                reason = "missing_fields"
                if listing.source_url and _is_root_domain_url(listing.source_url):
                    reason = "root_domain_url"
                elif not listing.source_url:
                    reason = "no_url"
                print(f"[SWARM] {name}: REJECTED [{reason}] make={listing.make} model={listing.model} url={listing.source_url}", flush=True)
                continue
            try:
                await gateway.ingest(listing)
                listing_count += 1
                if listing_count <= 3:
                    print(
                        f"[SWARM] {name}: VEHICLE {listing.make} {listing.model} "
                        f"{listing.year} EUR{listing.price_raw}",
                        flush=True,
                    )
            except Exception as exc:
                error_count += 1
                if error_count <= 3:
                    print(f"[SWARM] {name}: INGEST_ERR {exc}", flush=True)

    elapsed = time.monotonic() - t0
    rate = f"{listing_count / elapsed:.1f}" if elapsed > 0 else "0"
    print(
        f"[SWARM] {name}: {listing_count} vehicles extracted "
        f"({vector_used}, {pages_crawled} pages). PG insert rate: {rate}/sec",
        flush=True,
    )

    # Update dealer record
    status = "DONE" if listing_count > 0 else "NO_INVENTORY"
    await _update_spider_status(pg, dealer_id, name, country, status, vector_used, listing_count)

    # Mark as crawled in bloom (7-day TTL)
    await rdb.set(bloom_key, "1", ex=7 * 86400)

    log.info(
        "spider: %s done — vector=%s listings=%d errors=%d pages=%d elapsed=%.1fs",
        name, vector_used, listing_count, error_count, pages_crawled, elapsed,
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


async def _update_dealer_waf(
    pg: asyncpg.Pool,
    dealer_id: str,
    name: str,
    country: str,
    tier: int,
    waf_type: str,
) -> None:
    """Persist WAF detection and escalated proxy tier for future crawls."""
    try:
        await pg.execute("""
            UPDATE dealers
            SET proxy_tier    = $1,
                waf_type      = $2,
                last_block_at = now(),
                block_count   = block_count + 1,
                updated_at    = now()
            WHERE name = $3 AND country = $4
        """, tier, waf_type[:32], name, country)
    except Exception as exc:
        log.warning("spider: waf update failed dealer=%s: %s", name, exc)


# ── Consumer loop ─────────────────────────────────────────────────────────────

async def _consumer(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """Long-running consumer — all HTTP goes through StealthClient (curl_cffi)."""
    last_id = ">"
    while True:
        try:
            entries = await rdb.xreadgroup(
                groupname=_CG_SPIDER,
                consumername=f"spider-worker-{worker_id}",
                streams={_STREAM_IN: last_id},
                count=1,
                block=5000,
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
                                msg_id, fields, pg, rdb, gateway,
                            ),
                            timeout=1800.0,  # 30 min — full inventory pagination
                        )
                    except asyncio.TimeoutError:
                        name = fields.get("name", "?")
                        print(f"[SWARM] {name}: TIMEOUT (>30m)", flush=True)
                    except Exception as exc:
                        log.error("spider worker %d: unhandled error: %s", worker_id, exc)
                    finally:
                        try:
                            await rdb.xack(_STREAM_IN, _CG_SPIDER, msg_id)
                        except Exception:
                            pass


# ── Bootstrap ─────────────────────────────────────────────────────────────────

async def _backfill_pending_dealers(pg: asyncpg.Pool, rdb) -> int:
    """Queue all PENDING dealers with websites to the spider stream."""
    rows = await pg.fetch("""
        SELECT COALESCE(place_id, COALESCE(osm_id, 'id_' || id::text)) as dealer_id,
               name, country, website, proxy_tier, is_whale
        FROM dealers
        WHERE spider_status IN ('PENDING', 'FAILED') AND website IS NOT NULL
          AND (block_count < 3 OR last_block_at < now() - interval '30 days')
        ORDER BY
            CASE WHEN is_whale THEN 0 ELSE 1 END,  -- whales first
            proxy_tier ASC,                          -- cheap tiers first
            country, random()
        LIMIT 50000
    """)

    pipe = rdb.pipeline()
    for row in rows:
        pipe.xadd(
            _STREAM_IN,
            {
                "dealer_id": row["dealer_id"],
                "name": row["name"],
                "country": row["country"],
                "website": row["website"],
                "proxy_tier": str(row["proxy_tier"] or 0),
                "is_whale": "true" if row["is_whale"] else "false",
                "source": "BACKFILL",
            },
        )
    if rows:
        await pipe.execute()

    return len(rows)


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

    # Initialize Playwright semaphore globally
    global _PW_SEMAPHORE
    _PW_SEMAPHORE = asyncio.Semaphore(_PW_MAX_CONCURRENT)

    backfilled = await _backfill_pending_dealers(pg, rdb)
    log.info("spider: backfilled %d pending dealers to stream", backfilled)

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
