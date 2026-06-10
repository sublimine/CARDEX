"""
E2E proof of the dealer cage→entity consolidation (FASE E wiring fix), on the LIVE DB.

What it proves, end to end through the REAL A7 (the exact path ``make_live_seam`` runs
with ``entity_kind='dealer'``):
  (a) caging a dealer registers its ``source_entities`` row (kind='dealer'), and
  (b) every caged ``vehicles`` row carries a non-NULL ``entity_ulid`` set in the INSERT, so
  (c) ``entity_inventory`` (the per-entity API view) serves that inventory immediately.
Plus a PORTAL-CONTRACT guard: the same A7 run WITHOUT ``entity_kind`` must keep the
historical behavior (no entity row, ``entity_ulid`` NULL).

``pouw.nl`` — the entity closed manually on 2026-06-10 — is reported READ-ONLY as the
reference target state; it is never written. The synthetic dealer rows are purged at the
end (INSERT new + DELETE stale only; zero UPDATE of non-mutated rows).

    docker run -d --name cardex-redis-throwaway -p 56390:6379 redis:7-alpine
    python -m scripts.verify_entity_caging
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")

_DEALER = "verify-entity-caging.example"
_PORTAL = "verify-portal-contract.example"
_COUNTRY = "NL"
_N = 3


def _se_ulid(key: str) -> str:
    return "se_" + hashlib.md5(key.encode()).hexdigest()


def _payload(domain: str, i: int) -> dict:
    return {
        "make": "Audi", "model": f"A{i + 3}", "year": 2019 + i,
        "source_url": f"https://{domain}/occasions/audi-a{i + 3}-{i}",
        "source_listing_id": f"VERIFY{i}", "price_raw": 21000.0 + i * 500,
        "currency_raw": "EUR", "mileage_km": 40000 + i, "color": "black",
        "vin": "", "photo_urls": [], "source_country": _COUNTRY,
    }


async def _seed_and_consume(rdb, domain: str, n: int, entity_kind: str | None) -> int:
    for s in (a7.INGESTION_STREAM, a7.MEILI_SYNC_STREAM, a7.PRICE_EVENTS_STREAM):
        await rdb.delete(s)
    for i in range(n):
        await rdb.xadd(a7.INGESTION_STREAM, {
            "payload": json.dumps(_payload(domain, i)), "source": domain, "channel": "SCRAPER",
        })
    stats = await a7.run(
        database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
        limit=n, batch_size=n, block_ms=1500, entity_kind=entity_kind,
    )
    return stats.persisted


async def _purge(conn, domain: str) -> None:
    await conn.execute("DELETE FROM vehicles WHERE source_platform = $1", domain)
    await conn.execute("DELETE FROM source_entities WHERE source_key = $1", domain)


async def run() -> int:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    failures: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    try:
        # ── 0. reference target state: pouw.nl (READ-ONLY, never written) ─────────
        ulid_ref = _se_ulid("pouw.nl")
        async with pg.acquire() as conn:
            ref = await conn.fetchrow(
                "SELECT kind, country FROM source_entities WHERE source_key = 'pouw.nl'")
            ref_linked = await conn.fetchval(
                "SELECT count(*) FROM vehicles WHERE entity_ulid = $1", ulid_ref)
            ref_served = await conn.fetchval(
                "SELECT count(*) FROM entity_inventory WHERE entity_ulid = $1", ulid_ref)
        print(f"REFERENCE pouw.nl: entity={'present kind=' + ref['kind'] if ref else 'ABSENT'} "
              f"vehicles_linked={ref_linked} entity_inventory={ref_served}")

        # ── 1. DEALER cage through the REAL A7 (what make_live_seam now runs) ──────
        print(f"\nDEALER cage E2E ({_DEALER}, entity_kind='dealer'):")
        ulid = _se_ulid(_DEALER)
        async with pg.acquire() as conn:
            await _purge(conn, _DEALER)          # clean slate from any earlier run
            await _purge(conn, _PORTAL)
        persisted = await _seed_and_consume(rdb, _DEALER, _N, entity_kind="dealer")
        check(persisted == _N, f"A7 persisted {_N}/{_N}", f"persisted={persisted}")

        async with pg.acquire() as conn:
            ent = await conn.fetchrow(
                "SELECT entity_ulid, kind, country FROM source_entities WHERE source_key = $1",
                _DEALER)
            check(ent is not None and ent["kind"] == "dealer" and ent["entity_ulid"] == ulid,
                  "(a) source_entities row registered (kind='dealer', deterministic ulid)",
                  f"row={dict(ent) if ent else None}")
            rows = await conn.fetch(
                "SELECT entity_ulid FROM vehicles WHERE source_platform = $1", _DEALER)
            check(len(rows) == _N and all(r["entity_ulid"] == ulid for r in rows),
                  "(b) vehicles.entity_ulid non-NULL on every caged row (set in the INSERT)",
                  f"linked={sum(1 for r in rows if r['entity_ulid'])}/{len(rows)}")
            served = await conn.fetchval(
                "SELECT count(*) FROM entity_inventory WHERE entity_ulid = 'se_'||md5($1)",
                _DEALER)
            check(served >= _N, "(c) entity_inventory serves the caged inventory (API per-entity)",
                  f"count={served}")

        # ── 2. PORTAL contract guard: A7 without entity_kind stays byte-identical ──
        print(f"\nPORTAL contract guard ({_PORTAL}, entity_kind=None):")
        persisted_p = await _seed_and_consume(rdb, _PORTAL, 1, entity_kind=None)
        check(persisted_p == 1, "A7 persisted 1/1 (portal path)", f"persisted={persisted_p}")
        async with pg.acquire() as conn:
            no_ent = await conn.fetchval(
                "SELECT count(*) FROM source_entities WHERE source_key = $1", _PORTAL)
            check(no_ent == 0, "no source_entities row created for the portal run")
            null_link = await conn.fetchval(
                "SELECT count(*) FROM vehicles WHERE source_platform = $1 "
                "AND entity_ulid IS NULL", _PORTAL)
            check(null_link == 1, "portal row keeps entity_ulid NULL (historical contract)")

        return 0 if not failures else 1
    finally:
        # ── 3. cleanup: purge synthetic rows + throwaway streams (DELETE-only) ─────
        async with pg.acquire() as conn:
            await _purge(conn, _DEALER)
            await _purge(conn, _PORTAL)
        for s in (a7.INGESTION_STREAM, a7.MEILI_SYNC_STREAM, a7.PRICE_EVENTS_STREAM):
            await rdb.delete(s)
        await rdb.aclose()
        await pg.close()
        print("\ncleanup: synthetic rows purged, throwaway streams deleted")


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
