"""
CH discovery — Zefix via Open Data Basel-Stadt (Opendatasoft), name-filtered to dealers.

Switzerland's company register (Zefix) is fragmented across 26 cantons; Basel-Stadt
republishes it via Opendatasoft (geocoded, key-less). The CH register carries no
reliable NOGA activity code, so dealers are isolated by NAME using the trilingual
``dealer_terms`` (de/fr/it).

SCOPE: data.bs.ch dataset 100330 is Basel-Stadt only (~19k companies). The full
26-canton census is the ``data-bs.ch/.../all_cantons/companies_<KT>.csv`` mirror
(SOURCING_STRATEGY §5) — same shape, run per canton. This source loads the
verified-live BS slice; the mirror is the production sweep.

Identity rows (domain resolved later): registry_id = company_uid (CHE-...).

Usage:
    python -m scrapers.discovery.sources.ch_zefix_bs
    CH_MAX_PAGES=20 python -m scrapers.discovery.sources.ch_zefix_bs
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

from scrapers.discovery.dealer_terms import name_matches

log = logging.getLogger("ch_zefix_bs")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [ch_zefix_bs] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_API = "https://data.bs.ch/api/explore/v2.1/catalog/datasets/100330/records"
_SOURCE = "zefix_bs"
_SOURCE_LAYER = 3
_COUNTRY = "CH"
_PAGE = 100
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}


def _coords(rec: dict) -> tuple[float | None, float | None]:
    """Parse Opendatasoft coordinates ({lat,lon} | [lon,lat]) into (lat, lng)."""
    c = rec.get("coordinates")
    if isinstance(c, dict):
        return c.get("lat"), c.get("lon")
    if isinstance(c, (list, tuple)) and len(c) == 2:  # geojson [lon, lat]
        return c[1], c[0]
    return None, None


def to_candidate(rec: dict) -> dict:
    """Map one Zefix-BS record to a discovery candidate (pure)."""
    lat, lng = _coords(rec)
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "name": (rec.get("company_legal_name") or "").strip() or None,
        "address": (rec.get("street") or rec.get("address") or "").strip() or None,
        "city": (rec.get("municipality") or rec.get("locality") or "").strip() or None,
        "postcode": (str(rec.get("plz")) if rec.get("plz") else "").strip() or None,
        "lat": lat,
        "lng": lng,
        "registry_id": (rec.get("company_uid") or "").strip() or None,
        "external_refs": {"canton": "BS", "register_url": rec.get("url_cantonal_register")},
    }


_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,$8,$9,$10,$11::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def run(*, max_pages: int = 0) -> int:
    max_pages = max_pages or int(os.environ.get("CH_MAX_PAGES", "20"))
    inserted = 0
    scanned = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for page in range(max_pages):
                r = await client.get(_API, params={"limit": _PAGE, "offset": page * _PAGE}, headers=_HDR)
                if r.status_code != 200:
                    log.warning("page=%d http=%d — stop", page, r.status_code)
                    break
                results = r.json().get("results", [])
                if not results:
                    break
                scanned += len(results)
                for rec in results:
                    name = rec.get("company_legal_name") or ""
                    if not name_matches(name, _COUNTRY):  # name-filter: no reliable NOGA
                        continue
                    cand = to_candidate(rec)
                    if not cand["registry_id"]:
                        continue
                    await pool.execute(
                        _UPSERT, cand["country"], cand["source_layer"], cand["source"],
                        cand["name"], cand["address"], cand["city"], cand["postcode"],
                        cand["lat"], cand["lng"], cand["registry_id"],
                        json.dumps(cand["external_refs"]),
                    )
                    inserted += 1
                if len(results) < _PAGE:
                    break
            log.info("DONE ch_zefix_bs scanned=%d dealer_matches_upserted=%d", scanned, inserted)
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run())
