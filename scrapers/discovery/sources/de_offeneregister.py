"""
DE discovery — OffeneRegister (Handelsregister open data), name-filtered to dealers.

The German Handelsregister has no reliable activity code, so dealers are isolated
by NAME (Autohaus/KFZ/Automobile…) via the German ``dealer_terms``. OffeneRegister
republishes it two ways (SOURCING_STRATEGY §1):
  * SQL API  https://db.offeneregister.de (datasette, CSV/JSON)  ← this connector
  * dump     https://daten.offeneregister.de/openregister.db.gz (~773 MB SQLite)

STATUS (2026-06-07): the SQL API returns 502 (down) from here, and the 773 MB dump
is impractical to stream+query in this sandbox. So this connector is BUILT and
transform-tested but its LIVE LOAD IS BLOCKED — ``run()`` probes the API and, on
failure, returns 0 with a logged BLOCKED reason rather than inventing data. DE is
NOT discovery-empty regardless: it already holds ~45k candidates from other
sources. Run this when the SQL API recovers, or process the dump on the VPS.

The datasette schema (table ``company``, columns ``company_number`` / ``name`` /
``registered_office``) is `[ASUMIDO]` from OffeneRegister docs — verify against the
live API before depending on the exact column names.

Identity rows: registry_id = company_number (HRB/HRA).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

from scrapers.discovery.dealer_terms import terms_for

log = logging.getLogger("de_offeneregister")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [de_offeneregister] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_SQL_API = os.environ.get("OFFENEREGISTER_API", "https://db.offeneregister.de/de_openregister.json")
_SOURCE = "offeneregister"
_SOURCE_LAYER = 3
_COUNTRY = "DE"
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}


def to_candidate(row: dict) -> dict:
    """Map one OffeneRegister company row to a discovery candidate (pure)."""
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "name": (row.get("name") or "").strip() or None,
        "address": (row.get("registered_office") or row.get("address") or "").strip() or None,
        "city": (row.get("registered_office") or "").strip() or None,
        "postcode": None,
        "registry_id": (str(row.get("company_number")) if row.get("company_number") else "").strip() or None,
        "external_refs": {"register": "handelsregister"},
    }


def _sql(term: str, limit: int) -> str:
    """Datasette SQL: companies whose name carries a dealer term. term is from our
    controlled dealer_terms list (not user input) → safe to interpolate."""
    return (
        "SELECT company_number, name, registered_office FROM company "
        f"WHERE lower(name) LIKE '%{term}%' LIMIT {int(limit)}"
    )


async def run(*, per_term: int = 0) -> int:
    per_term = per_term or int(os.environ.get("DE_PER_TERM", "200"))
    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=40.0, follow_redirects=True) as client:
            for term in terms_for(_COUNTRY):
                try:
                    r = await client.get(_SQL_API, params={"sql": _sql(term, per_term)}, headers=_HDR)
                except httpx.HTTPError as exc:
                    log.warning("BLOCKED: OffeneRegister SQL API unreachable (%s) — "
                                "run when it recovers or process the dump on VPS", type(exc).__name__)
                    return inserted
                if r.status_code != 200:
                    log.warning("BLOCKED: OffeneRegister SQL API HTTP %d (term=%s) — "
                                "down now; DE already has ~45k candidates from other sources",
                                r.status_code, term)
                    return inserted
                rows = r.json().get("rows", [])
                for row in rows:
                    cand = to_candidate(row if isinstance(row, dict) else {})
                    if not cand["registry_id"]:
                        continue
                    await pool.execute(
                        "INSERT INTO discovery_candidates (domain,country,source_layer,source,url,"
                        "name,address,city,postcode,phone,email,lat,lng,registry_id,external_refs) "
                        "VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb) "
                        "ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL "
                        "DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'",
                        cand["country"], cand["source_layer"], cand["source"], cand["name"],
                        cand["address"], cand["city"], cand["postcode"], cand["registry_id"],
                        json.dumps(cand["external_refs"]),
                    )
                    inserted += 1
            log.info("DONE de_offeneregister upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run())
