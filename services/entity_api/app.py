"""CARDEX Entity Inventory API.

Per-entity inventory encapsulation: every platform/dealer (a `source_entity`) exposes
its OWN live inventory endpoint, sellable in isolation, plus a global index.

This is a VIEW over cardex-pg (no data copy): endpoints read `source_entities`,
the `entity_inventory` view, and `vehicle_events` directly. Read-only.

Run:
    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
      uvicorn services.entity_api.app:app --host 127.0.0.1 --port 8088

Design notes:
  - Cursor pagination (keyset on source_url) — stable, no OFFSET scans.
  - Pool kept small (max 4) to respect the RAM-constrained host (~780MB free).
  - Inventory is live: it reflects vehicle_index/vehicles as the delta updates them.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, command_timeout=30)
    try:
        yield
    finally:
        await _pool.close()


app = FastAPI(title="CARDEX Entity Inventory API", version="1.0", lifespan=lifespan)


def _envelope(data: Any, meta: dict | None = None) -> dict:
    return {"success": True, "data": data, "error": None, "meta": meta or {}}


async def _entity_or_404(conn: asyncpg.Connection, ulid: str) -> asyncpg.Record:
    row = await conn.fetchrow("SELECT * FROM source_entities WHERE entity_ulid = $1", ulid)
    if row is None:
        raise HTTPException(status_code=404, detail=f"entity {ulid} not found")
    return row


@app.get("/v1/health")
async def health() -> dict:
    async with _pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM source_entities")
    return _envelope({"status": "ok", "entities": n})


@app.get("/v1/entities")
async def list_entities(
    country: str | None = None,
    kind: str | None = Query(None, pattern="^(platform|dealer)$"),
    tier: str | None = Query(None, pattern="^(T1|T2|T3)$"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
) -> dict:
    """List source entities with their live inventory_count. Cursor = last source_key."""
    where = ["($1::text IS NULL OR country = $1)",
             "($2::text IS NULL OR kind = $2)",
             "($3::text IS NULL OR defense_tier = $3)",
             "($4::text IS NULL OR source_key > $4)"]
    sql = f"""
      WITH cnt AS (
        SELECT entity_ulid, count(*) AS n FROM (
          SELECT entity_ulid FROM vehicle_index WHERE entity_ulid IS NOT NULL
          UNION ALL
          SELECT entity_ulid FROM vehicles WHERE entity_ulid IS NOT NULL
        ) z GROUP BY entity_ulid
      )
      SELECT se.entity_ulid, se.source_key, se.kind, se.domain, se.country,
             se.defense_tier, se.waf, se.config_ref, COALESCE(c.n, 0) AS inventory_count
      FROM source_entities se
      LEFT JOIN cnt c USING (entity_ulid)
      WHERE {' AND '.join(where)}
      ORDER BY se.source_key
      LIMIT {limit}
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(sql, country, kind, tier, cursor)
    data = [dict(r) for r in rows]
    next_cursor = data[-1]["source_key"] if len(data) == limit else None
    return _envelope(data, {"count": len(data), "next_cursor": next_cursor})


@app.get("/v1/entities/{ulid}")
async def get_entity(ulid: str) -> dict:
    """Entity fiche: metadata + live inventory_count + 24h delta summary."""
    async with _pool.acquire() as conn:
        ent = await _entity_or_404(conn, ulid)
        inv = await conn.fetchval(
            "SELECT count(*) FROM entity_inventory WHERE entity_ulid = $1", ulid)
        delta = await conn.fetchrow(
            """SELECT
                 count(*) FILTER (WHERE event_type='SEEN' AND ts > now()-interval '24 hours') AS seen_24h,
                 count(*) FILTER (WHERE event_type='GONE' AND ts > now()-interval '24 hours') AS gone_24h,
                 max(ts) AS last_event
               FROM vehicle_events WHERE source_domain = $1""",
            ent["domain"])
    out = dict(ent)
    out["inventory_count"] = inv
    out["delta_24h"] = {"seen": delta["seen_24h"], "gone": delta["gone_24h"],
                        "last_event": delta["last_event"]}
    return _envelope(out)


@app.get("/v1/entities/{ulid}/inventory")
async def entity_inventory(
    ulid: str,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
) -> dict:
    """The sellable live inventory of ONE entity. Cursor = last source_url (keyset)."""
    async with _pool.acquire() as conn:
        await _entity_or_404(conn, ulid)
        rows = await conn.fetch(
            f"""SELECT source_url, country, title, make, model, year, price, currency,
                       mileage_km, thumb_url, status, seen_at, detail_level
                FROM entity_inventory
                WHERE entity_ulid = $1 AND ($2::text IS NULL OR source_url > $2)
                ORDER BY source_url
                LIMIT {limit}""",
            ulid, cursor)
    data = [dict(r) for r in rows]
    next_cursor = data[-1]["source_url"] if len(data) == limit else None
    return _envelope(data, {"entity_ulid": ulid, "count": len(data), "next_cursor": next_cursor})


@app.get("/v1/entities/{ulid}/delta")
async def entity_delta(
    ulid: str,
    since: str | None = Query(None, description="ISO timestamp; default last 7 days"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    """Altas/bajas (SEEN/GONE) of one entity — feeds clients tracking changes."""
    async with _pool.acquire() as conn:
        ent = await _entity_or_404(conn, ulid)
        rows = await conn.fetch(
            f"""SELECT event_type, url_original AS source_url, ts
                FROM vehicle_events
                WHERE source_domain = $1
                  AND ts >= COALESCE($2::timestamptz, now() - interval '7 days')
                ORDER BY ts DESC
                LIMIT {limit}""",
            ent["domain"], since)
    return _envelope([dict(r) for r in rows],
                     {"entity_ulid": ulid, "domain": ent["domain"], "count": len(rows)})


@app.get("/v1/inventory")
async def global_inventory(
    country: str | None = None,
    make: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
) -> dict:
    """Global platform index across all entities. Cursor = last source_url (keyset)."""
    sql = f"""
      SELECT entity_ulid, source_url, country, title, make, model, year, price, currency,
             status, detail_level, seen_at
      FROM entity_inventory
      WHERE ($1::text IS NULL OR country = $1)
        AND ($2::text IS NULL OR make ILIKE $2)
        AND ($3::text IS NULL OR source_url > $3)
      ORDER BY source_url
      LIMIT {limit}
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(sql, country, make, cursor)
    data = [dict(r) for r in rows]
    next_cursor = data[-1]["source_url"] if len(data) == limit else None
    return _envelope(data, {"count": len(data), "next_cursor": next_cursor})


@app.get("/v1/alerts")
async def list_alerts(
    status: str | None = None,
    signal: str | None = None,
    entity_ulid: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    """Operator alerts feed (internal channel the dashboard reads). Newest first."""
    sql = f"""
      SELECT alert_id, entity_ulid, source_key, stage, signal, severity, status,
             evidence, remediation_action, remediation_result, attempts, created_at, updated_at
      FROM operator_alerts
      WHERE ($1::text IS NULL OR status = $1)
        AND ($2::text IS NULL OR signal = $2)
        AND ($3::text IS NULL OR entity_ulid = $3)
      ORDER BY created_at DESC
      LIMIT {limit}
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(sql, status, signal, entity_ulid)
    return _envelope([dict(r) for r in rows], {"count": len(rows)})


@app.exception_handler(HTTPException)
async def _http_exc(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"success": False, "data": None, "error": exc.detail, "meta": {}})
