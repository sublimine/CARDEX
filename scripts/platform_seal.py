"""Shared persistence + verification tail for the PROXY-FREE platform connectors.

Each ``seal_<platform>.py`` owns the platform-specific bits (enumeration / faceting and
rich-field parsing). This module owns the homogeneous tail every platform shares, so the
delta invariant lives in ONE place, never re-implemented per connector:

  - cage rich pointers under a ``kind='platform'`` source_entity (``cage_inventory``),
  - reconcile (GONE + DELETE stale) ONLY on a COMPLETE cycle — a bounded ``--sample`` run
    is INSERT-only, because a partial set must never GONE-mark listings it simply did not
    reach (``scrapers/common/indexer.py`` doctrine: delete_stale only on a clean full cycle),
  - verify the per-entity API surface (the ``entity_inventory`` view the FastAPI reads)
    actually serves the caged rows with rich fields,
  - a 2-way count helper for the count_verify gate (declared total vs facet-sum).

PROXY-FREE, curl_cffi Chrome session is the connector's job; this is PG/Redis only.
"""
from __future__ import annotations

import json
import re
import sys

from scrapers.common.indexer import _hash_urls
from scrapers.dealer_scraping.inventory_harvester import _entity_ulid, cage_inventory

_LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def parse_ldjson_vehicle(html: str, url: str) -> dict:
    """schema.org Car/Vehicle ld+json -> cage-shape dict. ``offers.price`` is the CASH price
    (the structured-data sale price, NOT the financing /mois) — the price-trap-safe field used
    by the French SSR platforms (L'Argus, ParuVendu) whose detail pages also show a monthly
    simulator. Returns {url, title, price, year, km}; missing fields stay None."""
    make = model = name = year = km = price = None
    for m in _LDJSON.finditer(html or ""):
        try:
            d = json.loads(m.group(1))
        except (ValueError, TypeError):
            continue
        for o in (d if isinstance(d, list) else [d]):
            if not isinstance(o, dict) or o.get("@type") not in ("Car", "Vehicle"):
                continue
            name = o.get("name")
            brand = o.get("brand")
            make = brand.get("name") if isinstance(brand, dict) else brand
            model = o.get("model") if isinstance(o.get("model"), str) else None
            year = o.get("vehicleModelDate") or o.get("modelDate")
            odo = o.get("mileageFromOdometer")
            km = odo.get("value") if isinstance(odo, dict) else odo
            off = o.get("offers") or {}
            if isinstance(off, list):
                off = off[0] if off else {}
            price = off.get("price") if isinstance(off, dict) else None
            break
        if price is not None or name is not None:
            break
    title = name or (" ".join(str(x) for x in (make, model) if x).strip() or None)
    return {
        "url": url,
        "title": title,
        "price": int(re.sub(r"\D", "", str(price))) if price not in (None, "") else None,
        "year": int(str(year)[:4]) if year and str(year)[:4].isdigit() else None,
        "km": int(re.sub(r"\D", "", str(km))) if km not in (None, "") else None,
    }

# Windows consoles default to cp1252 and choke on accented listing titles (é, ü) and arrows.
# Make every platform connector's stdout UTF-8 safe at import time (single point of repair).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass


def to_cage(listing: dict) -> dict:
    """Adapt a parser-shape dict (source_url/make/model/variant/year/mileage_km/price_raw)
    into the cage shape (url/title/price/year/km). Tolerates already-cage-shaped dicts."""
    if "url" in listing and "source_url" not in listing:
        return listing
    title = " ".join(str(listing[k]) for k in ("make", "model", "variant")
                     if listing.get(k)).strip() or None
    return {
        "url": listing.get("source_url") or listing.get("url") or "",
        "title": title or listing.get("title"),
        "price": listing.get("price_raw") if listing.get("price_raw") is not None
                 else listing.get("price"),
        "year": listing.get("year"),
        "km": listing.get("mileage_km") if listing.get("mileage_km") is not None
              else listing.get("km"),
    }


async def cage_platform(pool, rdb, domain: str, country: str, listings: list[dict], *,
                        config_ref: str, complete: bool) -> dict:
    """Cage ``listings`` (cage-shape) under the platform entity; reconcile iff ``complete``.

    Returns {served, new, gone, ent}. ``complete=False`` (the E2E sample path) is INSERT-only.
    """
    cc = (country or "")[:2]
    caged = await cage_inventory(pool, rdb, domain, cc, listings,
                                 config_ref=config_ref, kind="platform")
    ent = _entity_ulid(domain)
    gone = 0
    if complete:
        keep = list(_hash_urls([li["url"] for li in listings if li.get("url")]).keys())
        async with pool.acquire() as c:
            async with c.transaction():
                stale = await c.fetch(
                    "SELECT url_hash,url_original FROM vehicle_index "
                    "WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))", ent, keep)
                if stale:
                    await c.execute(
                        "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                        "SELECT h,u,$3,$4,'GONE' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                        [r["url_hash"] for r in stale], [r["url_original"] for r in stale], domain, cc)
                    await c.execute(
                        "DELETE FROM vehicle_index WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))",
                        ent, keep)
                    gone = len(stale)
    async with pool.acquire() as c:
        served = await c.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)
    return {"served": served, "new": caged["new"], "gone": gone, "ent": ent,
            "discovered": caged["discovered"]}


async def verify_api(pool, ent: str, *, sample: int = 5) -> dict:
    """Prove the per-entity API view (entity_inventory) serves the entity's rows with rich
    fields. Mirrors exactly what GET /v1/entities/{ulid}/inventory returns (the API is a thin
    keyset read over this view). Returns served count, rich-field coverage, and sample rows."""
    async with pool.acquire() as c:
        served = await c.fetchval(
            "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ent)
        with_price = await c.fetchval(
            "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1 AND price IS NOT NULL", ent)
        with_year = await c.fetchval(
            "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1 AND year IS NOT NULL", ent)
        rows = await c.fetch(
            "SELECT source_url, title, year, price, currency, mileage_km, detail_level "
            "FROM entity_inventory WHERE entity_ulid=$1 ORDER BY source_url LIMIT $2", ent, sample)
        kind = await c.fetchval("SELECT kind FROM source_entities WHERE entity_ulid=$1", ent)
    return {"served": served, "with_price": with_price, "with_year": with_year,
            "kind": kind, "sample": [dict(r) for r in rows]}


def print_verdict(name: str, *, declared: int | None, way2_label: str, way2: int | None,
                  served: int, api: dict, price_trap: str) -> None:
    """Uniform end-of-run report block for every platform."""
    print(f"\n========== {name} — VERDICT ==========")
    print(f"  count_verify (>=2 ways):")
    print(f"    declared total          = {declared}")
    print(f"    {way2_label:<24}= {way2}")
    if declared and way2:
        diff = abs(declared - way2) / max(declared, 1) * 100
        print(f"    agreement               = {100 - diff:.1f}% (delta {diff:.2f}%)")
    print(f"  cage->API per-entity:")
    print(f"    entity kind             = {api['kind']}")
    print(f"    entity_inventory served = {api['served']}  (with_price={api['with_price']} "
          f"with_year={api['with_year']})")
    print(f"  price trap: {price_trap}")
    for r in api["sample"][:5]:
        print(f"    [{r['detail_level']}] {str(r['title'])[:42]:<42} "
              f"{r['year']} {r['price']} {r['currency']} {r['mileage_km']}km")
