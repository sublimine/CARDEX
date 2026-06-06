"""
A9 Entity Resolver (partial: VIN cross-source layer) — ``vehicles`` → ``entity_matches``.

Why partial (see P0_EXECUTION_REPORT §P0-4 for the full rationale):

  * The blueprint's A9 is the Go ``quality`` validators V21 (cosine-embedding
    multilingual *dealer* resolution, 615 LOC) + V12 (cross-source VIN dedup).
    Both live in the dead Go→SQLite pipeline and write ``dealer_entity`` (SQLite),
    never the PG ``entities``/``entity_matches`` tables (which is why both are 0).
  * Deterministic *dealer* dedup yields nothing here: ``discovery_candidates`` is
    already exact-unique on ``(domain,country)`` and ``(source,registry_id,country)``
    by DB constraint — the only remaining dealer matches are FUZZY (name variants
    across registry/domain rows), which is exactly what V21's embeddings do. That
    layer needs the embedder runtime (BGE-M3 / nomic via ollama) → deferred to P1.
  * ``entities`` population is coupled to the KYC/billing subsystem
    (``vault_dek_id NOT NULL``, Stripe, kyc_status) — a separate concern, also P1.

This module ships the part that is deterministic, high-precision, needs no embedder
and no vault, and writes the real PG ``entity_matches`` table: **cross-source VIN
resolution** (V12). When the same VIN appears in ``vehicles`` under two different
``source_platform`` values, those listings are the same physical car seen on two
marketplaces — an exact, confidence-1.0 match. It produces rows the moment
``vehicles`` carries cross-source VIN overlap (i.e. once A6→A7 runs at scale).

Pure pairing (``vin_group_matches``) is unit-tested; the asyncpg reader/writer is
the thin live shell, mirroring the rest of the pipeline's injection style.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

MATCH_TYPE = "VEHICLE"
MATCH_METHOD = "vin_exact"
CONFIDENCE = 1.0

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")


@dataclass(frozen=True)
class VehicleRef:
    """One ``vehicles`` row's identity for matching."""

    vehicle_ulid: str
    source_platform: str


@dataclass(frozen=True)
class Match:
    """One resolved cross-source pair, ready to upsert into ``entity_matches``."""

    entity_a_id: str
    entity_a_source: str
    entity_b_id: str
    entity_b_source: str
    vin: str


def vin_group_matches(vin: str, refs: list[VehicleRef]) -> list[Match]:
    """
    Pair every cross-source listing of one VIN to the group's canonical (first) row.

    Pure. Returns [] unless the VIN spans ≥2 *distinct* source platforms (a single
    platform re-listing the same VIN is not a cross-source dealer match — that is
    L2's own fingerprint dedup, not entity resolution). The canonical anchor is the
    lexicographically smallest ULID so the pairing is stable and idempotent across
    runs regardless of row order.
    """
    distinct_sources = {r.source_platform for r in refs}
    if len(refs) < 2 or len(distinct_sources) < 2:
        return []
    ordered = sorted(refs, key=lambda r: r.vehicle_ulid)
    anchor = ordered[0]
    matches: list[Match] = []
    for other in ordered[1:]:
        if other.source_platform == anchor.source_platform:
            continue  # same-platform dup is fingerprint's job, not entity resolution
        matches.append(Match(
            entity_a_id=anchor.vehicle_ulid, entity_a_source=anchor.source_platform,
            entity_b_id=other.vehicle_ulid, entity_b_source=other.source_platform,
            vin=vin,
        ))
    return matches


_SELECT_VIN_GROUPS = """
SELECT vin, vehicle_ulid, source_platform
FROM vehicles
WHERE vin IS NOT NULL AND vin <> ''
  AND vin IN (
    SELECT vin FROM vehicles
    WHERE vin IS NOT NULL AND vin <> ''
    GROUP BY vin
    HAVING count(DISTINCT source_platform) > 1
  )
ORDER BY vin
"""

_UPSERT_MATCH = """
INSERT INTO entity_matches (
    match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source,
    confidence, match_method, match_fields, validated
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,TRUE)
ON CONFLICT (match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source)
DO NOTHING
"""


async def resolve(pool, *, limit: int = 0) -> int:
    """
    Scan ``vehicles`` for cross-source VIN groups and upsert their pairs.

    Idempotent (``ON CONFLICT DO NOTHING`` on the natural key). Returns the number
    of match rows inserted this run. ``limit`` > 0 caps inserts (local validation).
    """
    groups: dict[str, list[VehicleRef]] = {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_VIN_GROUPS)
    for r in rows:
        groups.setdefault(r["vin"], []).append(
            VehicleRef(r["vehicle_ulid"], r["source_platform"])
        )

    inserted = 0
    async with pool.acquire() as conn:
        for vin, refs in groups.items():
            for m in vin_group_matches(vin, refs):
                res = await conn.execute(
                    _UPSERT_MATCH,
                    MATCH_TYPE, m.entity_a_id, m.entity_a_source, m.entity_b_id,
                    m.entity_b_source, CONFIDENCE, MATCH_METHOD,
                    json.dumps({"vin": m.vin}),
                )
                if res.endswith("1"):  # "INSERT 0 1" → a new row
                    inserted += 1
                    if limit and inserted >= limit:
                        log.info("entity_resolver hit limit=%d", limit)
                        return inserted
    log.info("entity_resolver done: %d cross-source VIN matches inserted", inserted)
    return inserted


async def run(*, database_url: str | None = None, limit: int = 0) -> int:
    from scrapers.common.indexer import make_pg

    pool = await make_pg(database_url or _DB_URL)
    try:
        return await resolve(pool, limit=limit)
    finally:
        await pool.close()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    n = asyncio.run(run(limit=int(os.environ.get("ENTITY_LIMIT", "0"))))
    print(f"entity_matches inserted: {n}")


if __name__ == "__main__":
    main()
