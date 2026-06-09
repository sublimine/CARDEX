"""
Mass registry harvest — millions of auto-trade entities from open gov registries.

Discovery scale (the 2M+ floor) lives in the national company registries filtered by
auto-trade activity code, NOT in per-site browser crawls. These are free JSON APIs;
the only trick is beating each API's result cap by slicing (department x activity).

FR — recherche-entreprises.api.gouv.fr (open, key-less). Caps total_results at 10000
per query, so we slice by ``departement`` x NAF code (each slice < 10k, verified: Paris
45.11Z = 8553). per_page max = 25. Identity candidates (no website in the registry; the
domain is resolved downstream by name_to_domain). Codes:
  45.11Z commerce de voitures et de véhicules automobiles légers   (DEALERS - core)
  45.19Z commerce d'autres véhicules automobiles                    (DEALERS - trucks/etc)
  45.20A entretien et réparation de véhicules automobiles légers    (garages - breadth)

High internal async concurrency (semaphore) so a full national sweep is minutes, not hours.

    python -m scrapers.discovery.sources.mass_registry                 # FR full, dealer codes
    MASS_CODES=45.11Z,45.19Z,45.20A python -m scrapers.discovery.sources.mass_registry
    MASS_CONC=16 python -m scrapers.discovery.sources.mass_registry
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

log = logging.getLogger("mass_registry")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s [mass_registry] %(message)s")

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_FR_API = "https://recherche-entreprises.api.gouv.fr/search"
_FR_CODES = [c.strip() for c in os.environ.get("MASS_CODES", "45.11Z,45.19Z,45.20A").split(",") if c.strip()]
_CONC = int(os.environ.get("MASS_CONC", "12"))
_PER_PAGE = 25  # FR API hard max
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}

# FR departments: 01-19, 21-95, 2A, 2B (Corsica), 971-976 (DOM).
_FR_DEPTS: list[str] = (
    [f"{d:02d}" for d in range(1, 20)]
    + ["2A", "2B"]
    + [f"{d:02d}" for d in range(21, 96)]
    + ["971", "972", "973", "974", "976"]
)

_UPSERT_IDENTITY = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,3,$2,NULL,$3,$4,$5,$6,NULL,NULL,NULL,NULL,$7,$8::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


def fr_to_candidate(rec: dict, code: str) -> dict | None:
    """Map a recherche-entreprises company to an identity candidate (pure)."""
    siren = (rec.get("siren") or "").strip()
    name = (rec.get("nom_complet") or rec.get("nom_raison_sociale") or "").strip() or None
    if not siren or not name:
        return None
    siege = rec.get("siege") or {}
    addr = (siege.get("adresse") or siege.get("geo_adresse") or "").strip() or None
    return {
        "country": "FR",
        "source": "registry:fr_sirene",
        "name": name,
        "address": addr,
        "city": (siege.get("libelle_commune") or "").strip() or None,
        "postcode": (siege.get("code_postal") or "").strip() or None,
        "registry_id": siren,
        "external_refs": {
            "naf": code,
            "etablissements": rec.get("nombre_etablissements_ouverts"),
            "date_creation": rec.get("date_creation"),
            "closed": bool(rec.get("date_fermeture")),
        },
    }


async def _get(client: httpx.AsyncClient, params: dict, *, retries: int = 4) -> dict:
    for attempt in range(retries + 1):
        try:
            r = await client.get(_FR_API, params=params, headers=_HDR)
            if r.status_code == 429 and attempt < retries:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < retries:
                await asyncio.sleep(0.6 * (2 ** attempt))
                continue
            raise
    return {}


async def harvest_fr_slice(client: httpx.AsyncClient, pool: asyncpg.Pool,
                           code: str, dept: str, stats: dict) -> None:
    """Paginate one (code, departement) slice fully and upsert every company."""
    page = 1
    written = 0
    while True:
        j = await _get(client, {"activite_principale": code, "departement": dept,
                                "per_page": _PER_PAGE, "page": page})
        results = j.get("results") or []
        if not results:
            break
        total_pages = int(j.get("total_pages") or 1)
        for rec in results:
            cand = fr_to_candidate(rec, code)
            if not cand:
                continue
            try:
                await pool.execute(
                    _UPSERT_IDENTITY, cand["country"], cand["source"], cand["name"],
                    cand["address"], cand["city"], cand["postcode"], cand["registry_id"],
                    json.dumps(cand["external_refs"]),
                )
                written += 1
            except Exception as exc:  # noqa: BLE001 — one bad row must not abort the slice
                log.debug("upsert fail siren=%s: %s", cand["registry_id"], exc)
        if page >= total_pages:
            break
        page += 1
    stats[f"{code}:{dept}"] = written
    if written:
        log.info("FR %s dept=%s -> %d", code, dept, written)


async def run_fr() -> int:
    pool = await asyncpg.create_pool(_DSN, min_size=4, max_size=12)
    sem = asyncio.Semaphore(_CONC)
    stats: dict[str, int] = {}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            async def _slice(code: str, dept: str) -> None:
                async with sem:
                    try:
                        await harvest_fr_slice(client, pool, code, dept, stats)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("FR %s dept=%s errored: %s", code, dept, exc)

            tasks = [_slice(code, dept) for code in _FR_CODES for dept in _FR_DEPTS]
            log.info("FR mass harvest: %d slices (%d codes x %d depts), conc=%d",
                     len(tasks), len(_FR_CODES), len(_FR_DEPTS), _CONC)
            await asyncio.gather(*tasks)
    finally:
        await pool.close()
    total = sum(stats.values())
    log.info("DONE mass_registry FR upserted=%d across %d slices", total, len(stats))
    return total


if __name__ == "__main__":
    asyncio.run(run_fr())
