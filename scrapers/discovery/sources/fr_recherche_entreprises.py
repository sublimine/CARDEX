"""
FR discovery — recherche-entreprises.api.gouv.fr (annuaire-entreprises).

The geocoded, key-less INSEE-backed company API. It is the lever that breaks the
FR mono-culture (84% of candidates were raw SIRENE): same INSEE base, but a
*different* orthogonal access path with lat/lng, segmented per department.

The API caps a query at 10,000 results, so enumeration is per (NAF code ×
``departement``) — each French department holds far fewer than the cap. Filter to
the automotive NAF codes (45.11Z sale of cars, 45.19Z sale of other vehicles).

Identity rows (domain resolved later): registry_id = SIREN.

Usage:
    python -m scrapers.discovery.sources.fr_recherche_entreprises
    FR_DEPTS=75,69,13 FR_MAX_PAGES=4 python -m scrapers.discovery.sources.fr_recherche_entreprises
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

log = logging.getLogger("fr_recherche")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [fr_recherche] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_API = "https://recherche-entreprises.api.gouv.fr/search"
_SOURCE = "recherche_entreprises"
_SOURCE_LAYER = 3
_COUNTRY = "FR"
_NAF = tuple(os.environ.get("FR_NAF", "45.11Z,45.19Z").split(","))
_PER_PAGE = 25
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}

# The 101 French departments (metropolitan 01-95 incl. Corsica 2A/2B, + overseas).
_ALL_DEPTS: tuple[str, ...] = tuple(
    [f"{n:02d}" for n in range(1, 96) if n != 20] + ["2A", "2B", "971", "972", "973", "974", "976"]
)
# Default to a representative metropolitan sample for a bounded validation load;
# the full sweep is FR_DEPTS=all (production).
_DEFAULT_DEPTS = ("75", "69", "13", "33", "59", "44", "31", "06", "67", "35")


def _depts() -> tuple[str, ...]:
    raw = os.environ.get("FR_DEPTS", "").strip()
    if not raw:
        return _DEFAULT_DEPTS
    if raw.lower() == "all":
        return _ALL_DEPTS
    return tuple(d.strip() for d in raw.split(",") if d.strip())


def _coords(siege: dict) -> tuple[float | None, float | None]:
    """Parse siege.coordonnees ('lat,lng') into floats, or (None, None)."""
    raw = (siege or {}).get("coordonnees")
    if not raw or "," not in str(raw):
        return None, None
    try:
        lat, lng = str(raw).split(",", 1)
        return float(lat), float(lng)
    except (ValueError, TypeError):
        return None, None


def to_candidate(result: dict) -> dict:
    """Map one recherche-entreprises result to a discovery candidate (pure)."""
    siege = result.get("siege") or {}
    lat, lng = _coords(siege)
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "name": (result.get("nom_complet") or result.get("nom_raison_sociale") or "").strip() or None,
        "address": (siege.get("adresse") or "").strip() or None,
        "city": (siege.get("commune") or "").strip() or None,
        "postcode": (siege.get("code_postal") or "").strip() or None,
        "lat": lat,
        "lng": lng,
        "registry_id": (result.get("siren") or "").strip() or None,
        "external_refs": {
            "naf": result.get("activite_principale"),
            "departement": siege.get("departement"),
            "etat": result.get("etat_administratif"),
        },
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


async def _fetch_page(client: httpx.AsyncClient, naf: str, dept: str, page: int) -> list[dict]:
    r = await client.get(_API, params={
        "activite_principale": naf, "departement": dept,
        "per_page": _PER_PAGE, "page": page,
    }, headers=_HDR)
    if r.status_code != 200:
        return []
    return r.json().get("results", [])


async def run(*, depts: tuple[str, ...] | None = None, max_pages: int = 0) -> int:
    depts = depts or _depts()
    max_pages = max_pages or int(os.environ.get("FR_MAX_PAGES", "4"))
    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for naf in _NAF:
                for dept in depts:
                    for page in range(1, max_pages + 1):
                        results = await _fetch_page(client, naf, dept, page)
                        if not results:
                            break
                        for res in results:
                            cand = to_candidate(res)
                            if not cand["registry_id"]:
                                continue
                            await pool.execute(
                                _UPSERT, cand["country"], cand["source_layer"], cand["source"],
                                cand["name"], cand["address"], cand["city"], cand["postcode"],
                                cand["lat"], cand["lng"], cand["registry_id"],
                                json.dumps(cand["external_refs"]),
                            )
                            inserted += 1
                        if len(results) < _PER_PAGE:
                            break
                    log.info("naf=%s dept=%s cumulative_upserted=%d", naf, dept, inserted)
            log.info("DONE fr_recherche upserted=%d depts=%d", inserted, len(depts))
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run())
