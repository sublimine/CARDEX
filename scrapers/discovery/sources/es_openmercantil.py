"""
ES discovery — OpenMercantil (ex-OpenBorme), CNAE automotive sectors.

Spain has no free public mercantile API à la France; OpenMercantil exposes the
BORME (mercantile register) as REST JSON, keyed by CNAE. Filter to the automotive
sectors: 4511 (sale of cars/light vehicles), 4519 (sale of other vehicles).

CAVEAT (SOURCING_STRATEGY §2): OpenMercantil's CNAE coverage is partial/biased
(skewed to recent incorporations/coops), so this is an ORTHOGONAL source that
breaks single-source dependency, not a complete census. Rate limit ~200 req/day/IP.

Identity rows (domain resolved later): registry_id = CIF.

Usage:
    python -m scrapers.discovery.sources.es_openmercantil
    ES_CNAE=4511,4519 ES_MAX_PAGES=10 python -m scrapers.discovery.sources.es_openmercantil
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

log = logging.getLogger("es_openmercantil")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [es_openmercantil] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_API = "https://openmercantil.es/api/v1/sector/{cnae}/companies"
_SOURCE = "openmercantil"
_SOURCE_LAYER = 3
_COUNTRY = "ES"
_CNAE = tuple(os.environ.get("ES_CNAE", "4511,4519").split(","))
_LIMIT = 20
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}


def to_candidate(item: dict, cnae: str) -> dict:
    """Map one OpenMercantil company to a discovery candidate (pure)."""
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "name": (item.get("name") or "").strip() or None,
        "address": None,
        "city": (item.get("province") or "").strip() or None,
        "postcode": None,
        "registry_id": (item.get("cif") or "").strip() or None,
        "external_refs": {
            "cnae": item.get("cnae_code") or cnae,
            "slug": item.get("slug"),
            "province": item.get("province"),
        },
    }


_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def run(*, max_pages: int = 0) -> int:
    max_pages = max_pages or int(os.environ.get("ES_MAX_PAGES", "10"))
    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for cnae in _CNAE:
                url = _API.format(cnae=cnae.strip())
                for page in range(max_pages):
                    r = await client.get(url, params={"limit": _LIMIT, "offset": page * _LIMIT}, headers=_HDR)
                    if r.status_code != 200:
                        log.warning("cnae=%s page=%d http=%d — stop", cnae, page, r.status_code)
                        break
                    items = r.json().get("items", [])
                    if not items:
                        break
                    for item in items:
                        cand = to_candidate(item, cnae)
                        if not cand["registry_id"]:
                            continue
                        await pool.execute(
                            _UPSERT, cand["country"], cand["source_layer"], cand["source"],
                            cand["name"], cand["address"], cand["city"], cand["postcode"],
                            cand["registry_id"], json.dumps(cand["external_refs"]),
                        )
                        inserted += 1
                    if len(items) < _LIMIT:
                        break
                log.info("cnae=%s cumulative_upserted=%d", cnae, inserted)
            log.info("DONE es_openmercantil upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run())
