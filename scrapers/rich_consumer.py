"""
A7 Rich Persister (``rich_consumer``) — stream:ingestion_raw → vehicles (L2).

Python implementation of the rich-persistence contract that
``services/pipeline/cmd/pipeline/main.go`` *specifies* but cannot run: that Go
service has no ``go.mod``, no ``pkg/{fx,h3,bloom}``, and the compose references a
``services/pipeline/Dockerfile`` that does not exist (verified 2026-06-06). The
audit found ``vehicles=30`` precisely because nothing consumed
``stream:ingestion_raw``. This consumer closes that half of the L1→L2 seam on the
live Python→PG backbone, honoring the **exact same** C7 JSON contract so the Go
service stays a valid drop-in replacement if it is ever completed.

Faithful to main.go (the reference spec):
  * validate          make/model non-empty, year 1920-2027, deep-link source_url
  * fingerprint       VIN-priority sha256, else url-based (computeFingerprint)
  * FX → EUR          fx_eur.to_eur + outlier gate (500 .. 2_000_000) when known
  * INSERT vehicles   31 cols … ON CONFLICT (fingerprint_sha256) DO UPDATE
  * vin_history_cache LISTING / PRICE_CHANGE / MILEAGE when VIN present
  * downstream XADD    stream:meili_sync (+ price_events, best-effort)

Two deliberate, documented divergences from main.go:
  * Dedup uses the PG unique fingerprint (ON CONFLICT) instead of RedisBloom —
    correctness without the extra dependency; RedisBloom stays a future fast-path.
  * Unknown-FX rows are stored with NULL ``gross_physical_cost_eur`` rather than
    dropped (main.go fails-closed). EUR markets — the bulk — are identical.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
from datetime import datetime, timezone
from decimal import Decimal

import redis.asyncio as aioredis
from ulid import ULID

from scrapers.common import indexer
from scrapers.pipeline import fx_eur

log = logging.getLogger(__name__)

INGESTION_STREAM = "stream:ingestion_raw"
MEILI_SYNC_STREAM = "stream:meili_sync"
PRICE_EVENTS_STREAM = "stream:price_events"
CONSUMER_GROUP = "cg_pipeline"
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

_PRICE_FLOOR_EUR = Decimal(500)
_PRICE_CEIL_EUR = Decimal(2_000_000)

_INSERT_VEHICLE_SQL = """
INSERT INTO vehicles (
    vehicle_ulid, fingerprint_sha256, vin, source_id, source_platform, ingestion_channel,
    source_url, source_country, photo_urls, listing_status,
    make, model, variant, year, mileage_km, color, fuel_type, transmission, co2_gkm, power_kw,
    price_raw, currency_raw, gross_physical_cost_eur, lat, lng, h3_index_res4, h3_index_res7,
    raw_description, seller_type, seller_vat_id, lifecycle_status,
    last_price_eur, price_drop_count
) VALUES (
    $1, $2, $3, $4, $5, $6,
    $7, $8, $9, $10,
    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
    $21, $22, $23, $24, $25, $26, $27,
    $28, $29, $30, 'INGESTED',
    $23, 0
)
ON CONFLICT (fingerprint_sha256) DO UPDATE SET
    last_updated_at         = NOW(),
    price_raw               = EXCLUDED.price_raw,
    currency_raw            = EXCLUDED.currency_raw,
    gross_physical_cost_eur = EXCLUDED.gross_physical_cost_eur,
    listing_status          = EXCLUDED.listing_status,
    photo_urls              = COALESCE(EXCLUDED.photo_urls, vehicles.photo_urls),
    mileage_km              = EXCLUDED.mileage_km,
    price_drop_count        = CASE
        WHEN EXCLUDED.gross_physical_cost_eur < vehicles.last_price_eur
        THEN vehicles.price_drop_count + 1
        ELSE vehicles.price_drop_count
    END,
    last_price_eur          = EXCLUDED.gross_physical_cost_eur
RETURNING vehicle_ulid, thumb_url,
          (xmax = 0) AS is_insert,
          (gross_physical_cost_eur < last_price_eur AND xmax != 0) AS price_dropped,
          last_price_eur AS prev_price_eur
"""


# ── pure helpers ───────────────────────────────────────────────────────────────
def compute_fingerprint(vin: str, source_url: str, color: str, mileage_km: int) -> str:
    """VIN-priority fingerprint, else URL-based — verbatim from main.go computeFingerprint."""
    if vin:
        payload = f"vin:{vin}:{(color or '').lower()}:{mileage_km}"
        return hashlib.sha256(payload.encode()).hexdigest()
    if source_url:
        return hashlib.sha256(("url:" + source_url).encode()).hexdigest()
    payload = f"attr:{(color or '').lower()}:0:{mileage_km}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _is_deep_link(source_url: str) -> bool:
    from urllib.parse import urlparse

    try:
        return urlparse(source_url).path.rstrip("/") != ""
    except ValueError:
        return False


def validate_payload(p: dict) -> str | None:
    """Minimum-viable-vehicle gate (main.go) — returns a reject reason or None."""
    if not p.get("make") or not p.get("model"):
        return "missing_make_model"
    year = p.get("year") or 0
    if year < 1920 or year > 2027:
        return "unrealistic_year"
    source_url = p.get("source_url") or ""
    if not source_url:
        return "no_source_url"
    if not _is_deep_link(source_url):
        return "root_domain_url"
    return None


def resolve_source_id(p: dict) -> str:
    """
    Guarantee a non-empty source_id (vehicles.source_id is NOT NULL).

    H1: prefer the explicit source_id, then source_listing_id (A6 already derives
    that from the url_hash), then a hash of the source_url as a final guard so
    even a non-A6 producer can never violate the constraint.
    """
    sid = (p.get("source_id") or "").strip()
    if sid:
        return sid
    listing = (p.get("source_listing_id") or "").strip()
    if listing:
        return listing
    return hashlib.sha256((p.get("source_url") or "").encode()).hexdigest()[:32]


def _num(value) -> Decimal | None:
    """Coerce to Decimal for a numeric column, or None (never raises)."""
    if value in (None, "", 0, 0.0):
        return None
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _none_if_blank(value) -> str | None:
    s = (value or "")
    return s if s else None


def build_insert_args(
    p: dict,
    *,
    source: str,
    channel: str,
    rates: dict[str, Decimal] | None = None,
) -> tuple[list, Decimal | None, str]:
    """
    Build the ordered asyncpg args for the vehicles INSERT.

    Returns (args, eur, fingerprint). ``eur`` is None when no FX rate is known.
    Pure and deterministic — the testable core of persistence.
    """
    price_raw = _num(p.get("price_raw"))
    currency = (p.get("currency_raw") or "").upper()
    eur = fx_eur.to_eur(price_raw, currency, rates) if price_raw is not None else None

    vin = (p.get("vin") or "").strip()
    color = p.get("color") or ""
    mileage = int(p.get("mileage_km") or 0)
    fingerprint = compute_fingerprint(vin, p.get("source_url") or "", color, mileage)

    country = (p.get("source_country") or "").upper()[:2] or None
    photos = list(p.get("photo_urls") or [])

    args = [
        str(ULID()),                                  # $1 vehicle_ulid
        fingerprint,                                  # $2 fingerprint_sha256
        vin or None,                                  # $3 vin
        resolve_source_id(p),                         # $4 source_id (NOT NULL)
        source or "UNKNOWN",                          # $5 source_platform
        channel or "SCRAPER",                         # $6 ingestion_channel
        p.get("source_url"),                          # $7 source_url
        country,                                       # $8 source_country
        photos,                                        # $9 photo_urls (_text)
        p.get("listing_status") or "ACTIVE",          # $10 listing_status
        p.get("make"),                                # $11 make
        p.get("model"),                               # $12 model
        _none_if_blank(p.get("variant")),             # $13 variant
        int(p.get("year") or 0),                      # $14 year
        mileage,                                       # $15 mileage_km
        _none_if_blank(color),                        # $16 color
        _none_if_blank(p.get("fuel_type")),           # $17 fuel_type
        _none_if_blank(p.get("transmission")),        # $18 transmission
        int(p.get("co2_gkm") or 0),                   # $19 co2_gkm
        int(p.get("power_kw") or 0),                  # $20 power_kw
        price_raw if price_raw is not None else Decimal(0),  # $21 price_raw
        currency,                                      # $22 currency_raw
        eur,                                           # $23 gross_physical_cost_eur (+ last_price_eur)
        _num(p.get("lat")),                           # $24 lat
        _num(p.get("lng")),                           # $25 lng
        _none_if_blank(p.get("h3_index_res4")),       # $26 h3_index_res4 (deferred; no geo yet)
        _none_if_blank(p.get("h3_index_res7")),       # $27 h3_index_res7
        _none_if_blank(p.get("description_snippet")), # $28 raw_description
        _none_if_blank(p.get("seller_type")),         # $29 seller_type
        _none_if_blank(p.get("seller_vat_id")),       # $30 seller_vat_id
    ]
    return args, eur, fingerprint


class PersistResult:
    __slots__ = ("ulid", "fingerprint", "is_insert", "price_dropped", "prev_price_eur", "eur")

    def __init__(self, ulid, fingerprint, is_insert, price_dropped, prev_price_eur, eur):
        self.ulid = ulid
        self.fingerprint = fingerprint
        self.is_insert = is_insert
        self.price_dropped = price_dropped
        self.prev_price_eur = prev_price_eur
        self.eur = eur


async def persist_one(
    pool,
    p: dict,
    *,
    source: str,
    channel: str,
    rates: dict[str, Decimal] | None = None,
) -> tuple[PersistResult | None, str]:
    """Validate, FX-gate, and upsert one vehicle. Returns (result, reason)."""
    reason = validate_payload(p)
    if reason:
        return None, reason

    args, eur, fingerprint = build_insert_args(p, source=source, channel=channel, rates=rates)

    # Outlier gate only applies when EUR is known (main.go fail-closed → here store-with-null).
    if eur is not None and (eur < _PRICE_FLOOR_EUR or eur > _PRICE_CEIL_EUR):
        return None, "outlier_price"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_INSERT_VEHICLE_SQL, *args)
        if row is None:
            return None, "insert_no_row"
        result = PersistResult(
            row["vehicle_ulid"], fingerprint, row["is_insert"],
            row["price_dropped"], row["prev_price_eur"], eur,
        )
        if p.get("vin"):
            await _write_vin_history(conn, p, result, source)
    return result, "ok"


async def _write_vin_history(conn, p: dict, result: PersistResult, source: str) -> None:
    """Append LISTING / PRICE_CHANGE / MILEAGE events when a VIN is known (main.go)."""
    vin = p["vin"]
    event_date = datetime.now(timezone.utc).date()
    eur = result.eur
    mileage = int(p.get("mileage_km") or 0)

    if result.is_insert:
        data = json.dumps({
            "source_platform": source, "source_country": p.get("source_country"),
            "source_url": p.get("source_url"), "mileage_km": mileage,
            "price_eur": float(eur) if eur is not None else None,
            "make": p.get("make"), "model": p.get("model"), "year": p.get("year"),
        })
        await conn.execute(
            "INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence) "
            "VALUES ($1, 'LISTING', $2, $3::jsonb, $4, 0.95)",
            vin, event_date, data, source,
        )

    if result.price_dropped and result.prev_price_eur and eur is not None:
        data = json.dumps({
            "price_eur_prev": float(result.prev_price_eur), "price_eur_new": float(eur),
            "price_drop_eur": float(result.prev_price_eur - eur),
            "source_platform": source, "source_country": p.get("source_country"),
            "mileage_km": mileage,
        })
        await conn.execute(
            "INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence) "
            "VALUES ($1, 'PRICE_CHANGE', $2, $3::jsonb, $4, 1.0)",
            vin, event_date, data, source,
        )

    if mileage > 0:
        data = json.dumps({
            "mileage_km": mileage, "source_platform": source,
            "source_country": p.get("source_country"),
            "price_eur": float(eur) if eur is not None else None,
        })
        await conn.execute(
            "INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence) "
            "VALUES ($1, 'MILEAGE', $2, $3::jsonb, $4, 0.80) ON CONFLICT DO NOTHING",
            vin, event_date, data, source,
        )


async def _emit_downstream(rdb, p: dict, result: PersistResult, source: str) -> None:
    """Publish to meili_sync (critical) + price_events (best-effort), like main.go."""
    eur = result.eur
    meili = json.dumps({
        "vehicle_ulid": result.ulid, "make": p.get("make"), "model": p.get("model"),
        "variant": p.get("variant"), "year": p.get("year"), "mileage_km": p.get("mileage_km"),
        "fuel_type": p.get("fuel_type"), "transmission": p.get("transmission"),
        "color": p.get("color"), "price_eur": float(eur) if eur is not None else None,
        "source_country": p.get("source_country"), "source_platform": source,
        "source_url": p.get("source_url"), "thumbnail_url": p.get("thumbnail_url"),
        "listing_status": p.get("listing_status") or "ACTIVE",
    })
    await rdb.xadd(
        MEILI_SYNC_STREAM,
        {"vehicle_ulid": result.ulid, "payload": meili, "op": "upsert"},
        maxlen=5_000_000, approximate=True,
    )
    if eur is not None:
        await rdb.xadd(
            PRICE_EVENTS_STREAM,
            {
                "vehicle_ulid": result.ulid, "source_url": p.get("source_url") or "",
                "price_eur": str(eur), "make": p.get("make") or "",
                "model": p.get("model") or "", "year": str(p.get("year") or 0),
                "source_country": p.get("source_country") or "", "source_platform": source,
            },
            maxlen=5_000_000, approximate=True,
        )


class RichStats:
    __slots__ = ("persisted", "rejected", "errors")

    def __init__(self) -> None:
        self.persisted = 0
        self.rejected = 0
        self.errors = 0


def _decode(fields: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in fields.items():
        key = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
        val = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
        out[key] = val
    return out


async def process_message(
    pool, rdb, msg_id: str, fields: dict, stats: RichStats,
    *, rates: dict[str, Decimal] | None = None,
) -> None:
    """Parse the C7 envelope, persist, emit downstream, ACK (at-least-once)."""
    f = _decode(fields)
    raw = f.get("payload")
    if not raw:
        await rdb.xack(INGESTION_STREAM, CONSUMER_GROUP, msg_id)
        stats.rejected += 1
        return
    source = f.get("source") or "UNKNOWN"
    channel = f.get("channel") or "SCRAPER"
    try:
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        await rdb.xack(INGESTION_STREAM, CONSUMER_GROUP, msg_id)
        stats.rejected += 1
        return

    result, reason = await persist_one(pool, payload, source=source, channel=channel, rates=rates)
    if result is None:
        await rdb.xack(INGESTION_STREAM, CONSUMER_GROUP, msg_id)
        stats.rejected += 1
        log.debug("rich rejected reason=%s url=%s", reason, payload.get("source_url"))
        return

    await _emit_downstream(rdb, payload, result, source)
    await rdb.xack(INGESTION_STREAM, CONSUMER_GROUP, msg_id)
    stats.persisted += 1
    log.info("rich persisted ulid=%s insert=%s eur=%s", result.ulid, result.is_insert, result.eur)


async def ensure_group(rdb, stream: str, group: str) -> None:
    try:
        await rdb.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as exc:  # pragma: no cover
        if "BUSYGROUP" not in str(exc):
            raise


async def run(
    *,
    database_url: str | None = None,
    redis_url: str | None = None,
    batch_size: int = 50,
    block_ms: int = 5_000,
    limit: int = 0,
) -> RichStats:
    """Consume ``stream:ingestion_raw`` and persist rich vehicle records to PG."""
    pool = await indexer.make_pg(database_url)
    rdb = aioredis.from_url(redis_url or _REDIS_URL, decode_responses=True)
    rates = fx_eur.load_rates_from_env()
    stats = RichStats()
    consumer = f"{socket.gethostname()}:{os.getpid()}"

    await ensure_group(rdb, INGESTION_STREAM, CONSUMER_GROUP)
    log.info("rich_consumer start group=%s consumer=%s limit=%d", CONSUMER_GROUP, consumer, limit)
    try:
        while limit == 0 or stats.persisted < limit:
            resp = await rdb.xreadgroup(
                CONSUMER_GROUP, consumer, {INGESTION_STREAM: ">"},
                count=batch_size, block=block_ms,
            )
            if not resp:
                if limit:
                    break
                continue
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    try:
                        await process_message(pool, rdb, msg_id, fields, stats, rates=rates)
                    except Exception:  # noqa: BLE001 — one bad row must not kill the loop
                        stats.errors += 1
                        log.exception("rich_consumer message failed id=%s", msg_id)
                    if limit and stats.persisted >= limit:
                        break
        log.info("rich_consumer done persisted=%d rejected=%d errors=%d",
                 stats.persisted, stats.rejected, stats.errors)
        return stats
    finally:
        await rdb.aclose()
        await pool.close()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(
        database_url=os.environ.get("DATABASE_URL"),
        redis_url=os.environ.get("REDIS_URL"),
        batch_size=int(os.environ.get("PIPELINE_BATCH_SIZE", "50")),
        limit=int(os.environ.get("RICH_LIMIT", "0")),
    ))


if __name__ == "__main__":
    main()
