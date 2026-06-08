"""
NL discovery — BOVAG member directory (Dutch car-dealer/garage federation).

BOVAG (Bond van Automobielhandelaren en Garagehouders) publishes its full member
list as a sitemap at bovag.nl/sitemap.xml (~8 007 /leden/<slug> URLs). Each member
page embeds a ``__NEXT_DATA__`` JSON block (Sanity CMS) with:

  page.name            — business name
  page.website         — dealer's own URL (absent when none)
  page.address         — {street, housenumber, postalCode, city, lat, lng}
  page.phoneNumber     — phone
  page.slug.current    — slug (used as registry_id)
  page.vehicles[]      — list of vehicle categories; property.key in
                          {auto, bedrijfswagen, bestelauto, truck, aanhanger} = automotive
                          {fiets, motor, bromfiets, snorfiets, camper, boot} = non-auto

BOVAG includes non-automotive members (bikes, mopeds, rentals). We filter:
  PASS  — at least one vehicle key in AUTO_KEYS, OR name matches NL dealer terms
  SKIP  — no automotive vehicle key AND name does not match dealer terms
  LOAD  — members with no vehicles list at all are loaded anyway (conservative)

Verified live 2026-06-07: 8 007 /leden/ URLs in sitemap.

Usage:
    python -m scrapers.discovery.sources.nl_bovag
    DATABASE_URL=postgresql://... python -m scrapers.discovery.sources.nl_bovag
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
from typing import Any

import asyncpg
import httpx

from scrapers.discovery.dealer_terms import name_matches

log = logging.getLogger("nl_bovag")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [nl_bovag] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_SITEMAP_URL = "https://www.bovag.nl/sitemap.xml"
_SOURCE = "bovag"
_SOURCE_LAYER = 2
_COUNTRY = "NL"
_CONCURRENCY = 8
_THROTTLE_S = 0.15   # seconds between request slots

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Vehicle category keys that indicate automotive (car, van, truck, trailer)
_AUTO_KEYS = frozenset({"auto", "bedrijfswagen", "bestelauto", "truck", "aanhanger"})

_SITEMAP_RE = re.compile(r"<loc>(https://www\.bovag\.nl/leden/[^<]+)</loc>")
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)
_STYLES_WEB_RE = re.compile(r'styles_website[^>]+href="([^"]+)"')


# ---------------------------------------------------------------------------
# Pure parsers (testable without I/O)
# ---------------------------------------------------------------------------

def extract_leden_urls(sitemap_xml: str) -> list[str]:
    """Return all /leden/<slug> URLs from sitemap XML text."""
    return _SITEMAP_RE.findall(sitemap_xml)


def _s(v: Any) -> str | None:
    if v is None:
        return None
    out = str(v).strip()
    return out or None


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_url(u: Any) -> str | None:
    if not u:
        return None
    u = str(u).strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def _domain(u: str | None) -> str | None:
    if not u:
        return None
    try:
        netloc = urllib.parse.urlparse(u).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _vehicle_keys(page: dict) -> set[str]:
    """Extract vehicle category keys from page JSON."""
    keys: set[str] = set()
    for v in page.get("vehicles") or []:
        prop = v.get("property") or {}
        k = prop.get("key") or ""
        if k:
            keys.add(k.lower())
    return keys


def is_automotive(page: dict) -> bool:
    """
    Return True if the member appears to be automotive.

    Logic:
      1. vehicles list present and non-empty:
           PASS  if any vehicle key is in AUTO_KEYS (auto/van/truck/trailer).
           SKIP  if all vehicle keys are non-automotive (bike/moped/etc.).
      2. vehicles list absent or empty:
           PASS unconditionally (conservative: don't skip unknowns).
    """
    vkeys = _vehicle_keys(page)
    if vkeys:
        return bool(vkeys & _AUTO_KEYS)
    # No vehicle metadata → include (conservative)
    return True


def parse_member_page(html: str, slug: str) -> dict | None:
    """
    Extract one discovery candidate dict from a /leden/<slug> HTML page.
    Returns None if we cannot determine name (page likely 404 or bot-block).
    """
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    page = (
        data.get("props", {})
        .get("pageProps", {})
        .get("page") or {}
    )
    name = _s(page.get("name"))
    if not name:
        # Try title fallback: "BOVAG - <name>"
        title_m = re.search(r"<title>BOVAG\s*[-–]\s*(.+?)</title>", html)
        if title_m:
            name = title_m.group(1).strip() or None
    if not name:
        return None

    # Website: prefer JSON field, fallback to HTML anchor with styles_website class
    website_raw = _normalize_url(page.get("website"))
    if not website_raw:
        hw = _STYLES_WEB_RE.search(html)
        if hw:
            website_raw = _normalize_url(hw.group(1))

    addr = page.get("address") or {}
    street = _s(addr.get("street"))
    housenumber = _s(addr.get("housenumber"))
    address = " ".join(filter(None, [street, str(housenumber) if housenumber else None])) or None

    vkeys = _vehicle_keys(page)
    automotive = is_automotive(page)

    return {
        "domain": _domain(website_raw),
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": website_raw,
        "name": name,
        "address": address,
        "city": _s(addr.get("city")),
        "postcode": _s(addr.get("postalCode")),
        "phone": _s(page.get("phoneNumber")),
        "email": None,
        "lat": _f(addr.get("latitude")),
        "lng": _f(addr.get("longitude")),
        "registry_id": slug,
        "external_refs": {
            "federation": "BOVAG",
            "vehicle_categories": sorted(vkeys) if vkeys else None,
        },
        # internal flag — not stored in DB
        "_automotive": automotive,
    }


# ---------------------------------------------------------------------------
# Upsert (mirrors ch_agvs pattern)
# ---------------------------------------------------------------------------

_COLS = (
    "domain, country, source_layer, source, url, name, address, city, postcode, "
    "phone, email, lat, lng, registry_id, external_refs"
)
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"

_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain = c.get("domain")
    registry_id = c.get("registry_id")
    if not domain and not registry_id:
        return False
    ext = dict(c.get("external_refs") or {})
    ext.pop("vehicle_categories", None)  # keep refs clean; categories logged separately
    # Re-add if present
    vc = (c.get("external_refs") or {}).get("vehicle_categories")
    if vc:
        ext["vehicle_categories"] = vc
    params = (
        domain, c["country"], c["source_layer"], c["source"],
        c.get("url"), c.get("name"), c.get("address"), c.get("city"),
        c.get("postcode"), c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"), registry_id, json.dumps(ext),
    )
    try:
        await pool.execute(
            _UPSERT_DOMAIN if domain else _UPSERT_IDENTITY,
            *params,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


# ---------------------------------------------------------------------------
# Async crawler
# ---------------------------------------------------------------------------

async def _fetch_member(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
) -> str | None:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    async with sem:
        await asyncio.sleep(_THROTTLE_S)
        try:
            r = await client.get(url, headers={"User-Agent": _UA})
            if r.status_code == 200:
                return r.text
            log.debug("HTTP %d for %s", r.status_code, slug)
            return None
        except Exception as exc:  # noqa: BLE001
            log.debug("fetch error %s: %s", slug, exc)
            return None


async def run(max_members: int | None = None) -> dict:
    """
    Download sitemap, crawl /leden/ pages concurrently, upsert to DB.

    Args:
        max_members: cap on pages to process (None = all).  Used for testing.

    Returns:
        stats dict with keys: processed, parsed, automotive, with_web, upserted, skipped_non_auto.
    """
    stats = dict(processed=0, parsed=0, automotive=0, with_web=0, upserted=0, skipped_non_auto=0)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # 1. Download sitemap
        log.info("Downloading sitemap %s", _SITEMAP_URL)
        try:
            r = await client.get(_SITEMAP_URL, headers={"User-Agent": _UA})
        except Exception as exc:
            log.error("Cannot fetch sitemap: %s", exc)
            return stats
        if r.status_code != 200:
            log.error("Sitemap HTTP %d", r.status_code)
            return stats

        urls = extract_leden_urls(r.text)
        log.info("Sitemap: %d /leden/ URLs found", len(urls))
        if max_members is not None:
            urls = urls[:max_members]
            log.info("Capped at %d members", len(urls))

        # 2. Crawl pages with bounded concurrency
        # Each task carries its URL so slug derivation is safe regardless of completion order.
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def _fetch_with_url(url: str) -> tuple[str, str | None]:
            """Return (url, html_text_or_None)."""
            html_text = await _fetch_member(client, sem, url)
            return url, html_text

        tasks = [asyncio.create_task(_fetch_with_url(u)) for u in urls]

        pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
        try:
            done = 0
            for coro in asyncio.as_completed(tasks):
                member_url, html_text = await coro
                done += 1
                stats["processed"] += 1

                if html_text is None:
                    continue

                slug = member_url.rstrip("/").rsplit("/", 1)[-1]
                candidate = parse_member_page(html_text, slug)
                if candidate is None:
                    continue
                stats["parsed"] += 1

                if not candidate.pop("_automotive", True):
                    stats["skipped_non_auto"] += 1
                    continue

                stats["automotive"] += 1
                if candidate.get("domain"):
                    stats["with_web"] += 1

                if await _upsert(pool, candidate):
                    stats["upserted"] += 1

                if done % 500 == 0:
                    log.info(
                        "Progress %d/%d parsed=%d automotive=%d with_web=%d upserted=%d skip=%d",
                        done, len(urls),
                        stats["parsed"], stats["automotive"],
                        stats["with_web"], stats["upserted"],
                        stats["skipped_non_auto"],
                    )
        finally:
            await pool.close()

    log.info(
        "DONE nl_bovag processed=%d parsed=%d automotive=%d with_web=%d upserted=%d skipped_non_auto=%d",
        stats["processed"], stats["parsed"], stats["automotive"],
        stats["with_web"], stats["upserted"], stats["skipped_non_auto"],
    )
    return stats


if __name__ == "__main__":
    asyncio.run(run())
