"""
DE discovery — 11880.com dealer directory (Germany's largest business directory).

11880.com lists ~52,721 Autohaendler (car dealers) Germany-wide accessible without
anti-bot beyond a Chrome User-Agent.  Every listing page serves 50 entries via a
JSON-LD ItemList block that contains name, email, address, and phone.  The dealer's
OWN website is NOT in the listing — it lives on the individual detail page behind
``itemprop="url" content="..."``.

Strategy (RAM-safe, two-phase):
  Phase A — Listing sweep: iterate all ~1,055 pages, insert every dealer as an
            identity row (name + address + phone + email, no website yet).
            Registry-id comes from the 11880 path: /branchenbuch/<city>/<ID>/<slug>.
  Phase B — Detail enrichment: visit detail pages with capped concurrency
            (Semaphore ~ DETAIL_CONCURRENCY, default 6) and update the website
            field for rows that have one.  Stops when DETAIL_MAX_PAGES is reached
            (0 = unlimited).  Progress is logged every 250 pages.

Environment variables:
  DATABASE_URL          PostgreSQL DSN (default: dev)
  LISTING_THROTTLE      Seconds between listing pages (default: 0.25)
  DETAIL_THROTTLE       Seconds between detail batches (default: 0.5)
  DETAIL_CONCURRENCY    Concurrent detail fetches (default: 6)
  LISTING_MAX_PAGES     Stop listing after N pages — 0 = all (default: 0)
  DETAIL_MAX_PAGES      Stop detail enrichment after N detail fetches — 0 = all (default: 0)

Usage:
    python -m scrapers.discovery.sources.de_11880
    LISTING_MAX_PAGES=3 DETAIL_MAX_PAGES=30 python -m scrapers.discovery.sources.de_11880
"""
from __future__ import annotations

import asyncio
import html as html_mod
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request

import asyncpg

log = logging.getLogger("de_11880")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [de_11880] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
)
_BASE_LISTING = "https://www.11880.com/suche/autohaendler/deutschland"
_BASE_DETAIL = "https://www.11880.com"
_SOURCE = "11880"
_SOURCE_LAYER = 2
_COUNTRY = "DE"

_LISTING_THROTTLE = float(os.environ.get("LISTING_THROTTLE", "1.5"))
_DETAIL_THROTTLE = float(os.environ.get("DETAIL_THROTTLE", "0.6"))
_DETAIL_CONCURRENCY = int(os.environ.get("DETAIL_CONCURRENCY", "4"))
_LISTING_MAX_PAGES = int(os.environ.get("LISTING_MAX_PAGES", "0"))
_DETAIL_MAX_PAGES = int(os.environ.get("DETAIL_MAX_PAGES", "0"))
# Backoff on 429: wait this many seconds before retrying (doubles on consecutive 429s)
_BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "30.0"))

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "de-DE,de;q=0.9",
}


# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without network)
# ---------------------------------------------------------------------------

def _s(v: object) -> str | None:
    if v is None:
        return None
    out = str(v).strip()
    return out or None


def _normalize_url(u: str | None) -> str | None:
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _registry_id_from_path(path: str) -> str | None:
    """Extract the 11880 alphanumeric ID from a branchenbuch path.

    Pattern: /branchenbuch/<city>/<ID>/<slug>.html
    The ID is the third path segment, e.g. '120672194B27114587'.
    Returns '11880-<ID>' or None.
    """
    m = re.search(r"/branchenbuch/[^/]+/([A-Za-z0-9]+)/", path)
    if not m:
        return None
    return f"11880-{m.group(1)}"


def parse_listing_page(page_html: str) -> list[dict]:
    """Parse one 11880 listing HTML page into candidate dicts.

    Extracts the single JSON-LD ItemList block present on every results page.
    Returns a list of candidate dicts (no website — that requires detail fetch).
    """
    blocks = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        page_html, re.DOTALL,
    )
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # Tolerate both top-level ItemList and SearchResultsPage wrapper
        entity = data.get("mainEntity") or data
        if entity.get("@type") != "ItemList":
            continue
        items = entity.get("itemListElement", [])
        return [_listing_item_to_candidate(it) for it in items
                if _listing_item_to_candidate(it) is not None]
    return []


def _listing_item_to_candidate(item: dict) -> dict | None:
    """Convert one ItemList entry to a candidate dict."""
    business = item.get("item", item)
    name = _s(html_mod.unescape(business.get("name") or ""))
    if not name:
        return None

    # 11880 profile URL → extract registry_id
    profile_url = _s(business.get("url") or "")
    registry_id = None
    detail_path = None
    if profile_url:
        parsed = urllib.parse.urlparse(profile_url)
        registry_id = _registry_id_from_path(parsed.path)
        detail_path = parsed.path  # relative path for detail enrichment

    addr_obj = business.get("address") or {}
    street = _s(addr_obj.get("streetAddress"))
    postcode = _s(addr_obj.get("postalCode"))
    city = _s(addr_obj.get("addressLocality"))
    region = _s(addr_obj.get("addressRegion"))
    address_parts = [p for p in [street, postcode, city, region] if p]
    address = ", ".join(address_parts) if address_parts else None

    return {
        "domain": None,          # not available from listing
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": None,             # enriched in phase B
        "name": name,
        "address": address,
        "city": city,
        "postcode": postcode,
        "phone": _s(business.get("telephone")),
        "email": _s(business.get("email")),
        "lat": None,
        "lng": None,
        "registry_id": registry_id,
        "detail_path": detail_path,   # ephemeral — used for enrichment, not persisted
        "external_refs": {"profile": profile_url} if profile_url else {},
    }


def parse_detail_page(detail_html: str) -> dict:
    """Extract dealer website (and optionally lat/lng) from a detail page.

    Returns a dict with keys 'url', 'domain', 'lat', 'lng' (all may be None).
    """
    # Website: <meta itemprop="url" content="...">
    url_hits = re.findall(r'itemprop="url"\s+content="([^"]+)"', detail_html)
    url = _normalize_url(url_hits[0]) if url_hits else None
    # Filter out self-references to 11880
    if url and "11880.com" in url:
        url = None

    # Geo: from JSON-LD LocalBusiness on detail page
    lat = lng = None
    blocks = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        detail_html, re.DOTALL,
    )
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # May be wrapped: {"localBusiness": {...}}
        business = data.get("localBusiness") or data
        geo = business.get("geo") or {}
        if geo.get("latitude"):
            try:
                lat = float(geo["latitude"])
                lng = float(geo.get("longitude") or 0) or None
            except (TypeError, ValueError):
                pass
        if lat is not None:
            break

    return {"url": url, "domain": _domain(url), "lat": lat, "lng": lng}


def parse_total_pages(page_html: str) -> int:
    """Extract total result count from listing page, compute page count."""
    # <span id="hit-count">52721</span>  or similar
    m = re.search(r'id="hit-count"[^>]*>([\d\s,\.]+)<', page_html)
    if m:
        try:
            total = int(re.sub(r"[\s,\.]", "", m.group(1)))
            return max(1, (total + 49) // 50)
        except ValueError:
            pass
    # Fallback: look at pagination last page number
    pages = re.findall(r'[?&]page=(\d+)', page_html)
    if pages:
        try:
            return max(int(p) for p in pages)
        except ValueError:
            pass
    return 1055  # verified 2026-06-07 fallback


# ---------------------------------------------------------------------------
# Network layer (synchronous — RAM flat: one listing page at a time)
# ---------------------------------------------------------------------------

import random as _random

def _fetch(url: str, *, max_retries: int = 3) -> str:
    """Fetch URL with exponential backoff on 429 Too Many Requests."""
    backoff = _BACKOFF_BASE
    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 429:
                # Honour Retry-After if present (11880 uses this)
                retry_after_hdr = exc.headers.get("Retry-After", "")
                try:
                    wait = float(retry_after_hdr) + _random.uniform(5, 15)
                    log.warning("429 — Retry-After=%ss; waiting %.0fs (attempt %d/%d)",
                                retry_after_hdr, wait, attempt + 1, max_retries + 1)
                except (TypeError, ValueError):
                    jitter = _random.uniform(0, backoff * 0.2)
                    wait = backoff + jitter
                    log.warning("429 Too Many Requests — backing off %.0fs (attempt %d/%d)",
                                 wait, attempt + 1, max_retries + 1)
                time.sleep(wait)
                backoff = min(backoff * 2, 300.0)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            raise
    raise last_exc


# ---------------------------------------------------------------------------
# DB upsert (same two-route pattern as ch_agvs / de_gelbeseiten)
# ---------------------------------------------------------------------------

_COLS = (
    "domain, country, source_layer, source, url, name, address, city, postcode, "
    "phone, email, lat, lng, registry_id, external_refs"
)
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"

_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
# Update website on an existing row (domain-free) once we have the detail URL
_UPDATE_WEBSITE = """
UPDATE discovery_candidates
SET domain = $1, url = $2, lat = COALESCE(lat, $3), lng = COALESCE(lng, $4),
    last_seen = NOW()
WHERE source = $5 AND registry_id = $6 AND country = $7
  AND domain IS NULL
"""


async def _upsert_identity(pool: asyncpg.Pool, c: dict) -> bool:
    """Insert listing-only row (no domain).  Uses registry_id conflict key."""
    registry_id = c.get("registry_id")
    if not registry_id:
        return False
    params = (
        None,  # domain
        c["country"], c["source_layer"], c["source"],
        None,  # url
        c.get("name"), c.get("address"), c.get("city"), c.get("postcode"),
        c.get("phone"), c.get("email"),
        None, None,  # lat, lng
        registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    try:
        await pool.execute(_UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:
        log.warning("upsert_identity failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


async def _upsert_with_domain(pool: asyncpg.Pool, c: dict) -> bool:
    """Insert/update row that has a domain (from detail enrichment)."""
    domain = c.get("domain")
    registry_id = c.get("registry_id")
    if not domain:
        return False

    # Try domain-conflict upsert first
    params_domain = (
        domain, c["country"], c["source_layer"], c["source"],
        c.get("url"), c.get("name"), c.get("address"), c.get("city"), c.get("postcode"),
        c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"),
        registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    try:
        await pool.execute(_UPSERT_DOMAIN, *params_domain)
        return True
    except Exception as exc:
        log.warning("upsert_domain failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


async def _update_website(pool: asyncpg.Pool, registry_id: str, enrichment: dict) -> bool:
    """Patch the existing identity-only row with the discovered website."""
    domain = enrichment.get("domain")
    if not domain or not registry_id:
        return False
    try:
        status = await pool.execute(
            _UPDATE_WEBSITE,
            domain, enrichment.get("url"),
            enrichment.get("lat"), enrichment.get("lng"),
            _SOURCE, registry_id, _COUNTRY,
        )
        # asyncpg returns 'UPDATE N' — success if N > 0
        updated = int(status.split()[-1])
        return updated > 0
    except Exception as exc:
        log.warning("update_website failed registry_id=%r: %s", registry_id, exc)
        return False


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

async def run() -> dict:
    """Full two-phase run.  Returns stats dict."""
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)

    stats = {
        "listing_pages": 0,
        "parsed": 0,
        "upserted_identity": 0,
        "detail_fetched": 0,
        "with_web": 0,
        "web_updated": 0,
    }

    # -------------------------------------------------------------------------
    # Phase A: Listing sweep
    # -------------------------------------------------------------------------
    log.info("Phase A: Listing sweep — %s", _BASE_LISTING)

    # Page 1 (no ?page= param)
    try:
        html1 = _fetch(_BASE_LISTING)
    except Exception as exc:
        log.error("Failed to fetch listing page 1: %s", exc)
        await pool.close()
        return stats

    total_pages = parse_total_pages(html1)
    log.info("Total pages detected: %d (50 results/page)", total_pages)
    if _LISTING_MAX_PAGES and total_pages > _LISTING_MAX_PAGES:
        total_pages = _LISTING_MAX_PAGES
        log.info("LISTING_MAX_PAGES=%d — limiting to %d pages", _LISTING_MAX_PAGES, total_pages)

    candidates_p1 = parse_listing_page(html1)
    stats["listing_pages"] += 1
    # Keep detail_path for phase B; remove before upsert
    detail_queue: list[tuple[str, str]] = []  # (registry_id, detail_path)
    for c in candidates_p1:
        dp = c.pop("detail_path", None)
        stats["parsed"] += 1
        if await _upsert_identity(pool, c):
            stats["upserted_identity"] += 1
        if dp and c.get("registry_id"):
            detail_queue.append((c["registry_id"], dp))

    log.info("Page 1: parsed=%d upserted=%d", len(candidates_p1), stats["upserted_identity"])

    # Pages 2..N
    for page_num in range(2, total_pages + 1):
        time.sleep(_LISTING_THROTTLE)
        url = f"{_BASE_LISTING}?page={page_num}"
        try:
            page_html = _fetch(url)
        except Exception as exc:
            log.warning("Listing page %d fetch failed: %s", page_num, exc)
            continue

        candidates = parse_listing_page(page_html)
        if not candidates:
            log.info("Empty listing at page %d — stopping sweep", page_num)
            break

        stats["listing_pages"] += 1
        for c in candidates:
            dp = c.pop("detail_path", None)
            stats["parsed"] += 1
            if await _upsert_identity(pool, c):
                stats["upserted_identity"] += 1
            if dp and c.get("registry_id"):
                detail_queue.append((c["registry_id"], dp))

        if stats["listing_pages"] % 100 == 0:
            log.info(
                "Phase A progress: pages=%d parsed=%d upserted=%d",
                stats["listing_pages"], stats["parsed"], stats["upserted_identity"],
            )

    log.info(
        "Phase A complete: pages=%d parsed=%d upserted=%d detail_queue=%d",
        stats["listing_pages"], stats["parsed"], stats["upserted_identity"], len(detail_queue),
    )

    # -------------------------------------------------------------------------
    # Phase B: Detail enrichment (bounded concurrency)
    # -------------------------------------------------------------------------
    if not detail_queue:
        await pool.close()
        return stats

    cap = _DETAIL_MAX_PAGES if _DETAIL_MAX_PAGES else len(detail_queue)
    queue_slice = detail_queue[:cap]
    log.info(
        "Phase B: enriching %d detail pages (concurrency=%d throttle=%.2fs)",
        len(queue_slice), _DETAIL_CONCURRENCY, _DETAIL_THROTTLE,
    )

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)
    lock = asyncio.Lock()

    async def _enrich(registry_id: str, path: str) -> None:
        async with semaphore:
            detail_url = _BASE_DETAIL + path
            try:
                loop = asyncio.get_running_loop()
                detail_html = await loop.run_in_executor(None, _fetch, detail_url)
            except Exception as exc:
                log.debug("Detail fetch failed %s: %s", path, exc)
                async with lock:
                    stats["detail_fetched"] += 1
                return

            enrichment = parse_detail_page(detail_html)
            async with lock:
                stats["detail_fetched"] += 1
                if enrichment.get("domain"):
                    stats["with_web"] += 1
                    if await _update_website(pool, registry_id, enrichment):
                        stats["web_updated"] += 1
                if stats["detail_fetched"] % 250 == 0:
                    log.info(
                        "Phase B progress: fetched=%d with_web=%d updated=%d / total=%d",
                        stats["detail_fetched"], stats["with_web"],
                        stats["web_updated"], len(queue_slice),
                    )
            await asyncio.sleep(_DETAIL_THROTTLE)

    # Process in batches to avoid creating tens of thousands of coroutines at once
    BATCH = _DETAIL_CONCURRENCY * 4
    for i in range(0, len(queue_slice), BATCH):
        batch = queue_slice[i:i + BATCH]
        await asyncio.gather(*[_enrich(rid, dp) for rid, dp in batch])

    await pool.close()

    log.info(
        "DONE de_11880: listing_pages=%d parsed=%d upserted_identity=%d "
        "detail_fetched=%d with_web=%d web_updated=%d",
        stats["listing_pages"], stats["parsed"], stats["upserted_identity"],
        stats["detail_fetched"], stats["with_web"], stats["web_updated"],
    )
    return stats


if __name__ == "__main__":
    asyncio.run(run())
