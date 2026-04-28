"""
WordPress REST API harvester — extracts the FULL vehicle inventory of a
WordPress dealer site without scraping a single HTML page.

Insight: ~40% of EU dealer sites run WordPress. By default, every WP install
exposes the REST API at `/wp-json/wp/v2/`. From there:

  GET /wp-json/wp/v2/types
    → list of all post types (incl. custom Vehicle CPTs)
  GET /wp-json/wp/v2/{cpt}?per_page=100&page=N
    → paginated JSON of all listings with title, content, featured_media
  GET /wp-json/wp/v2/media/{id}
    → image URL + metadata

Compared to per-listing HTML scraping this is:
  • 100× fewer HTTP requests (one batch GET per page of 100 listings)
  • Structured data — no regex fragility
  • Includes content (description), title, slug, modification date

CPT detection — common vehicle CPT slugs:
    vehicle, vehicles, voiture, voitures, coche, coches, auto, autos,
    car, cars, fahrzeug, fahrzeuge, occasion, occasions, listing, stock,
    inventory, vehicule, vehicules

Usage:
    python -m scrapers.discovery.wp_rest_harvester

Environment:
    DATABASE_URL                postgres://...
    MEILI_URL                   http://localhost:7700
    MEILI_MASTER_KEY            cardex_meili_dev_only
    WP_HARVESTER_CONC           parallel domains      (default 8)
    WP_HARVESTER_PER_PAGE       per_page in REST      (default 100)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [wp_rest] %(message)s",
)
log = logging.getLogger("wp_rest")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_CONC = int(os.environ.get("WP_HARVESTER_CONC", "8"))
_PER_PAGE = int(os.environ.get("WP_HARVESTER_PER_PAGE", "100"))
_TIMEOUT = float(os.environ.get("WP_HARVESTER_TIMEOUT", "20"))

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
_HEADERS_MEILI = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}

# Custom post type slugs that commonly hold vehicle listings
_VEHICLE_CPT_HINTS = (
    "vehicle", "vehicles", "voiture", "voitures", "coche", "coches",
    "auto", "autos", "car", "cars", "fahrzeug", "fahrzeuge",
    "occasion", "occasions", "listing", "stock", "inventory",
    "vehicule", "vehicules", "auto-usate", "auto_usate", "stock-listing",
    "stock_listing", "annonce", "annonces", "anuncio", "anuncios",
)

_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_PRICE_NUM = re.compile(r"(\d{1,3}(?:[\s.,\u00a0]\d{3})+|\d{4,6})\s*€")
_RE_KM_NUM = re.compile(r"(\d{1,3}(?:[\s.,\u00a0]\d{3})+|\d{1,6})\s*km", re.I)
_RE_YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _RE_HTML_TAG.sub(" ", s or "")).strip()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


# ── REST exploration ─────────────────────────────────────────────────────────

async def _wp_root(client: httpx.AsyncClient, base: str) -> dict[str, Any] | None:
    """Probe /wp-json/ root and return the discovery doc, or None if not WP."""
    candidates = [
        f"{base}/wp-json/",
        f"{base}/?rest_route=/",
        f"{base}/index.php/wp-json/",
    ]
    for url in candidates:
        try:
            r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype.lower():
            continue
        try:
            return r.json()
        except Exception:
            continue
    return None


async def _list_post_types(client: httpx.AsyncClient, base: str) -> list[str]:
    """Return post type slugs that look like vehicle CPTs."""
    for endpoint in (
        f"{base}/wp-json/wp/v2/types",
        f"{base}/?rest_route=/wp/v2/types",
    ):
        try:
            r = await client.get(endpoint, headers=_HEADERS, timeout=_TIMEOUT)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        out: list[str] = []
        for slug, meta in data.items():
            slug_low = slug.lower()
            if any(h in slug_low for h in _VEHICLE_CPT_HINTS):
                out.append(slug)
        return out
    return []


async def _harvest_cpt(
    client: httpx.AsyncClient, base: str, cpt: str,
) -> list[dict[str, Any]]:
    """Paginate /wp-json/wp/v2/{cpt} until exhausted."""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        for endpoint in (
            f"{base}/wp-json/wp/v2/{cpt}?per_page={_PER_PAGE}&page={page}&_embed=1",
            f"{base}/?rest_route=/wp/v2/{cpt}&per_page={_PER_PAGE}&page={page}&_embed=1",
        ):
            try:
                r = await client.get(endpoint, headers=_HEADERS, timeout=_TIMEOUT)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                items = r.json()
            except Exception:
                continue
            if not isinstance(items, list) or not items:
                return out
            out.extend(items)
            break
        else:
            return out
        if len(out) > 50_000:  # safety cap
            return out
        page += 1
        if page > 1000:
            return out


# ── Item → Meili doc ─────────────────────────────────────────────────────────

def _meili_doc_from_item(item: dict[str, Any], country: str, domain: str) -> dict[str, Any] | None:
    link = item.get("link") or ""
    if not link:
        return None

    title = ""
    if isinstance(item.get("title"), dict):
        title = _strip_html(item["title"].get("rendered", ""))

    content_html = ""
    if isinstance(item.get("content"), dict):
        content_html = item["content"].get("rendered", "")
    description = _strip_html(content_html)

    # Featured image — _embedded.wp:featuredmedia[0].source_url
    image = None
    embedded = item.get("_embedded") or {}
    fm = embedded.get("wp:featuredmedia") or []
    if fm and isinstance(fm[0], dict):
        image = (
            fm[0].get("source_url")
            or fm[0].get("media_details", {}).get("sizes", {}).get("full", {}).get("source_url")
        )

    # Gallery — sometimes in ACF or meta
    gallery: list[str] = []
    acf = item.get("acf") or {}
    if isinstance(acf, dict):
        for k in ("gallery", "images", "photos", "vehicle_images"):
            v = acf.get(k)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and x.get("url"):
                        gallery.append(x["url"])
                    elif isinstance(x, str):
                        gallery.append(x)
    if image and image not in gallery:
        gallery.insert(0, image)

    # Best-effort price/km/year extraction from content
    price = None
    if m := _RE_PRICE_NUM.search(description):
        try:
            price = int(re.sub(r"[\s.,\u00a0]", "", m.group(1)))
            if not (1000 <= price <= 300_000):
                price = None
        except ValueError:
            pass

    km = None
    if m := _RE_KM_NUM.search(description):
        try:
            km = int(re.sub(r"[\s.,\u00a0]", "", m.group(1)))
            if not (0 < km < 500_000):
                km = None
        except ValueError:
            pass

    # ACF fields commonly hold structured data
    if isinstance(acf, dict):
        for k in ("price", "price_eur", "prix", "precio"):
            if v := acf.get(k):
                try:
                    price = int(float(str(v).replace(",", "").replace(" ", "")))
                except (ValueError, TypeError):
                    pass
                break
        for k in ("mileage", "mileage_km", "kilometrage", "km"):
            if v := acf.get(k):
                try:
                    km = int(float(str(v).replace(",", "").replace(" ", "")))
                except (ValueError, TypeError):
                    pass
                break

    year = None
    if m := _RE_YEAR.search(title + " " + description):
        try:
            y = int(m.group(1))
            if 1990 <= y <= 2027:
                year = y
        except ValueError:
            pass

    doc: dict[str, Any] = {
        "vehicle_ulid": f"vi{_url_hash(link)}",
        "source_url": link,
        "source_country": country,
        "source_platform": (domain.split(".")[0] if "." in domain else domain).upper(),
        "listing_status": "ACTIVE",
        "variant": title[:240] if title else None,
    }
    if image:
        doc["thumbnail_url"] = image
        doc["thumb_url"] = image
    if gallery:
        doc["gallery_urls"] = gallery[:30]
    if description:
        doc["description"] = description[:1500]
    if price:
        doc["price_eur"] = float(price)
    if km:
        doc["mileage_km"] = km
    if year:
        doc["year"] = year
    return doc


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def _push_meili(meili: httpx.AsyncClient, docs: list[dict]) -> None:
    if not docs:
        return
    r = await meili.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HEADERS_MEILI,
        json=docs,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili PUT %d: %d %s", len(docs), r.status_code, r.text[:200])


async def _harvest_domain(
    client: httpx.AsyncClient,
    meili: httpx.AsyncClient,
    pool: asyncpg.Pool,
    domain: str,
    country: str,
) -> int:
    base = f"https://{domain}"

    root = await _wp_root(client, base)
    if not root:
        return 0

    cpts = await _list_post_types(client, base)
    if not cpts:
        return 0

    log.info("WP %s: cpts=%s", domain, cpts)

    total = 0
    for cpt in cpts:
        items = await _harvest_cpt(client, base, cpt)
        if not items:
            continue
        log.info("WP %s/%s: %d items", domain, cpt, len(items))

        docs: list[dict] = []
        candidate_rows: list[tuple] = []
        for it in items:
            doc = _meili_doc_from_item(it, country, domain)
            if doc:
                docs.append(doc)
                if (link := doc.get("source_url")):
                    candidate_rows.append((
                        _url_hash(link), link, domain, country,
                    ))

        # Push to Meili
        for i in range(0, len(docs), 500):
            await _push_meili(meili, docs[i:i + 500])

        # Insert into vehicle_index too (so the pipeline knows about them)
        if candidate_rows:
            await pool.executemany(
                """
                INSERT INTO vehicle_index
                  (url_hash, url_original, source_domain, country, sitemap_source, last_seen)
                VALUES ($1, $2, $3, $4, 'wp_rest', NOW())
                ON CONFLICT (url_hash) DO NOTHING
                """,
                candidate_rows,
            )

        total += len(docs)

    return total


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4, command_timeout=120)
    fetch = httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        http2=True,
        limits=httpx.Limits(
            max_keepalive_connections=_CONC * 2,
            max_connections=_CONC * 4,
        ),
    )
    meili = httpx.AsyncClient(timeout=60.0)
    sem = asyncio.Semaphore(_CONC)

    rows = await pool.fetch(
        "SELECT DISTINCT domain, country FROM discovery_candidates "
        "WHERE domain IS NOT NULL AND sitemap_status IN ('found','none','pending') "
        "ORDER BY domain"
    )
    log.info("WP-REST harvest: %d domains to probe", len(rows))

    totals = {"domains": 0, "wp_sites": 0, "items": 0}
    t0 = time.monotonic()

    async def _process(row: asyncpg.Record) -> None:
        async with sem:
            try:
                n = await _harvest_domain(fetch, meili, pool, row["domain"], row["country"])
            except Exception as exc:
                log.debug("harvest %s: %s", row["domain"], exc)
                n = 0
            totals["domains"] += 1
            if n > 0:
                totals["wp_sites"] += 1
                totals["items"] += n
            if totals["domains"] % 50 == 0:
                el = time.monotonic() - t0
                log.info(
                    "progress: domains=%d wp_sites=%d items=%d (%.1fs)",
                    totals["domains"], totals["wp_sites"], totals["items"], el,
                )

    try:
        await asyncio.gather(*(_process(r) for r in rows))
        el = time.monotonic() - t0
        log.info(
            "DONE — domains=%d wp_sites=%d items=%d in %.1fs",
            totals["domains"], totals["wp_sites"], totals["items"], el,
        )
    finally:
        await fetch.aclose()
        await meili.aclose()
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
