"""
A6 Enricher (``enrich_worker``) — the L1 → L2 seam.

The audit found a triple gap that left ``vehicles`` stuck at 30 rows:

  * ``indexer.py`` (A5) publishes URL pointers to ``stream:enrich_pending`` as
    ``{h,u,s,c}`` (url_hash, url, source_key, country) — pointers only.
  * the rich consumer (A7) reads ``stream:ingestion_raw`` expecting a full
    ``vehiclePayload`` — a *different* stream, so nothing flows.
  * the ``enrich-worker`` container in ``docker-compose.yml`` ran
    ``-m enrich_worker`` against a module that did not exist.

This module is that missing bridge. For every pointer on ``enrich_pending`` it
fetches the listing through the anti-detection engine, parses it into a canonical
``VehicleRecord`` (reusing the verified ``generic_extractor.extract_listing``
cascade: fetch → parse → normalize → quality), maps it to the ``vehiclePayload``
contract (C7), and emits it to ``stream:ingestion_raw`` for the rich consumer.

H1 fix — ``vehicles.source_id`` is ``NOT NULL`` (``scripts/init-pg.sql``) but the
rich INSERT binds it as ``coalesce(source_id, source_listing_id)``. Scraper
listings frequently carry neither, so the row violated NOT NULL and was dropped
*silently*. A6 guarantees a non-empty ``source_listing_id`` by deriving it from
the ``url_hash`` (``h``, always present) when the listing has no platform id —
so the pointer can never be lost for want of an identifier.

Design mirrors ``indexer.py``: a pure, I/O-free transform (``record_to_payload``)
and a thin async run loop. The transport (``Fetcher``) is injected so the logic
is unit-testable against in-memory fixtures, exactly like ``generic_extractor``.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import socket
from decimal import Decimal

import redis.asyncio as aioredis

from scrapers.pipeline.generic_extractor import Fetcher, FetchResult, extract_listing
from scrapers.pipeline.schema import VehicleRecord

log = logging.getLogger(__name__)

# ── stream contract (verbatim from indexer.py / services/pipeline/main.go) ──────
ENRICH_STREAM = "stream:enrich_pending"      # A5 → A6 (C5)
INGESTION_STREAM = "stream:ingestion_raw"    # A6 → A7 (C7)
DLQ_STREAM = "stream:dlq"                     # irreparable parses
CONSUMER_GROUP = "cg_enrich"
INGESTION_MAXLEN = 5_000_000
DEFAULT_CHANNEL = "SCRAPER"                   # vehicles.ingestion_channel CHECK value
# Reclaim entries idle longer than this from the group PEL. A transient failure
# leaves a message un-ACKed; without reclaim XREADGROUP '>' never re-delivers it
# and the work is lost at scale. 60s is well above a healthy in-flight time, so
# reclaim never steals a message another consumer is actively processing.
RECLAIM_IDLE_MS = int(os.environ.get("ENRICH_RECLAIM_IDLE_MS", "60000"))

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Carries the per-message country (`c`) to the engine fetcher without breaking the
# url-only Fetcher contract. enrich_one sets it; make_engine_fetcher reads it to
# pick a country-appropriate identity. ContextVars propagate down awaited calls
# within the same task, so concurrent messages never cross-contaminate.
_enrich_country: contextvars.ContextVar[str] = contextvars.ContextVar(
    "enrich_country", default=""
)

# Failure reasons that are permanent for this listing (bad/garbage page) → DLQ +
# ACK. Anything else (transport fault, 5xx) is transient → leave un-ACKed so the
# consumer-group reclaim re-delivers it later.
_PERMANENT_PREFIXES = ("no_fields", "missing_critical", "rejected", "quality")


def _int_from(additional: dict[str, str], key: str) -> int:
    """Best-effort int from a free-text ``additional`` value, else 0."""
    raw = additional.get(key)
    if not raw:
        return 0
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits) if digits else 0


def _float_from(additional: dict[str, str], key: str) -> float:
    """Best-effort float from an ``additional`` value, else 0.0 (never raises)."""
    raw = additional.get(key)
    if raw in (None, ""):
        return 0.0
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def record_to_payload(
    record: VehicleRecord,
    *,
    source_key: str,
    url_hash: str,
) -> dict:
    """
    Map a canonical ``VehicleRecord`` (C6) to the ``vehiclePayload`` JSON (C7).

    Pure and deterministic — the single point that encodes the C6→C7 contract.
    Field names are verbatim from ``services/pipeline/main.go``'s json tags so the
    Go consumer and the Python rich consumer unmarshal it identically.

    H1: ``source_listing_id`` is guaranteed non-empty (real listing id, else the
    ``url_hash``) so the downstream ``coalesce(source_id, source_listing_id)``
    binding can never yield NULL and drop the row.
    """
    listing_id = record.source_listing_id or url_hash
    add = record.additional or {}
    price = record.price  # gross preferred, else net (schema.VehicleRecord.price)

    return {
        # identity
        "vin": record.vin or "",
        "source_url": record.source_url,
        "source_listing_id": listing_id,            # H1: never empty
        # vehicle
        "make": record.make or "",
        "model": record.model or "",
        "variant": add.get("variant", ""),
        "year": record.year or 0,
        "mileage_km": record.mileage_km or 0,
        "color": record.color or "",
        "fuel_type": record.fuel_type.value if record.fuel_type else "",
        "transmission": record.transmission.value if record.transmission else "",
        "body_type": record.body_type.value if record.body_type else "",
        "co2_gkm": _int_from(add, "co2_gkm"),
        "power_kw": record.power_kw or 0,
        # price
        "price_raw": float(price) if isinstance(price, Decimal) else 0.0,
        "currency_raw": record.currency or "",
        # location (populated only when a parser emits them into `additional`)
        "lat": _float_from(add, "lat"),
        "lng": _float_from(add, "lng"),
        "city": add.get("city", ""),
        "region": add.get("region", ""),
        "source_country": record.country,
        # seller
        "seller_type": add.get("seller_type", ""),
        "seller_name": add.get("seller_name", ""),
        "seller_vat_id": add.get("seller_vat_id", ""),
        # media
        "photo_urls": list(record.images),
        "thumbnail_url": record.images[0] if record.images else "",
        # scrape metadata
        "description_snippet": add.get("description", ""),
        "listing_status": add.get("listing_status", "ACTIVE"),
        # routing hint for the rich consumer (kept alongside the Redis `source`
        # field so the payload is self-describing if replayed from the DLQ)
        "source_platform": source_key,
    }


def _decode_fields(fields: dict) -> dict[str, str]:
    """Decode a Redis stream entry to ``str`` keys/values regardless of decode mode."""
    out: dict[str, str] = {}
    for k, v in fields.items():
        key = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
        val = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
        out[key] = val
    return out


async def enrich_one(
    fields: dict,
    fetcher: Fetcher,
    *,
    default_country: str = "",
) -> tuple[dict | None, str]:
    """
    Enrich one ``enrich_pending`` entry into a ``vehiclePayload`` (or a reason).

    Returns ``(payload, "ok")`` on success or ``(None, reason)`` where the reason
    names the failure stage (``fetch_error``, ``http_404``, ``no_fields``,
    ``missing_critical:...`` …) so the caller can route transient vs permanent.
    """
    f = _decode_fields(fields)
    url = f.get("u", "")
    url_hash = f.get("h", "")
    source_key = f.get("s") or ""
    country = f.get("c") or default_country

    if not url or not url_hash:
        return None, "rejected:malformed_pointer"

    # Thread the pointer's country to the engine fetcher (identity selection).
    _enrich_country.set(country)
    record, reason = await extract_listing(
        url, fetcher, country=country, source_domain=source_key or None
    )
    if record is None:
        return None, reason
    payload = record_to_payload(record, source_key=source_key, url_hash=url_hash)
    return payload, "ok"


def _is_permanent(reason: str) -> bool:
    return any(reason.startswith(p) for p in _PERMANENT_PREFIXES)


async def ensure_group(rdb: aioredis.Redis, stream: str, group: str) -> None:
    """Create the consumer group (and stream) idempotently; ignore BUSYGROUP."""
    try:
        await rdb.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as exc:  # pragma: no cover - depends on live redis
        if "BUSYGROUP" not in str(exc):
            raise


async def _emit(rdb: aioredis.Redis, payload: dict, source_key: str) -> None:
    """Publish one enriched payload to ``stream:ingestion_raw`` (C7 envelope)."""
    await rdb.xadd(
        INGESTION_STREAM,
        {
            "payload": json.dumps(payload, separators=(",", ":")),
            "source": source_key or "UNKNOWN",
            "channel": DEFAULT_CHANNEL,
        },
        maxlen=INGESTION_MAXLEN,
        approximate=True,
    )


async def _to_dlq(rdb: aioredis.Redis, fields: dict[str, str], reason: str) -> None:
    """Park an unrecoverable pointer on the DLQ stream for later inspection."""
    await rdb.xadd(
        DLQ_STREAM,
        {
            "agent": "enrich_worker",
            "reason": reason,
            "h": fields.get("h", ""),
            "u": fields.get("u", ""),
            "s": fields.get("s", ""),
            "c": fields.get("c", ""),
        },
        maxlen=1_000_000,
        approximate=True,
    )


class EnrichStats:
    """Mutable counters for one run — emitted, dlq, transient, drained."""

    __slots__ = ("emitted", "dlq", "transient")

    def __init__(self) -> None:
        self.emitted = 0
        self.dlq = 0
        self.transient = 0


async def process_message(
    rdb: aioredis.Redis,
    fetcher: Fetcher,
    msg_id: str,
    fields: dict,
    stats: EnrichStats,
    *,
    default_country: str = "",
) -> None:
    """
    Enrich + route one message: emit to ingestion_raw, DLQ, or leave for reclaim.

    At-least-once: ACK only after the payload is durably on ``ingestion_raw`` or
    parked on the DLQ. Transient failures are NOT ACKed so the group reclaim
    re-delivers them.
    """
    decoded = _decode_fields(fields)
    payload, reason = await enrich_one(fields, fetcher, default_country=default_country)

    if payload is not None:
        await _emit(rdb, payload, decoded.get("s", ""))
        await rdb.xack(ENRICH_STREAM, CONSUMER_GROUP, msg_id)
        stats.emitted += 1
        return

    if _is_permanent(reason):
        await _to_dlq(rdb, decoded, reason)
        await rdb.xack(ENRICH_STREAM, CONSUMER_GROUP, msg_id)
        stats.dlq += 1
        log.info("enrich dropped url=%s reason=%s", decoded.get("u"), reason)
        return

    # transient (fetch_error / http_5xx): do not ACK — let reclaim retry later
    stats.transient += 1
    log.warning("enrich transient url=%s reason=%s (no ack)", decoded.get("u"), reason)


async def reclaim_pending(
    rdb: aioredis.Redis,
    fetcher: Fetcher,
    stats: EnrichStats,
    *,
    consumer: str,
    idle_ms: int,
    count: int,
    default_country: str = "",
) -> int:
    """
    XAUTOCLAIM one batch of PEL entries idle > ``idle_ms`` and reprocess them.

    XREADGROUP '>' only ever delivers brand-new ids, so a message a consumer read
    but never ACKed (transient fetch fault, crash) sits in the group's pending list
    forever — silent loss at scale (H1). This reclaims the genuinely-stranded ones
    so at-least-once actually holds. Tombstones (entry deleted from the stream after
    being read) come back with empty fields → ACK to clear them from the PEL.
    Returns the number of live messages reprocessed.
    """
    try:
        res = await rdb.xautoclaim(
            ENRICH_STREAM, CONSUMER_GROUP, consumer,
            min_idle_time=idle_ms, start_id="0-0", count=count,
        )
    except aioredis.ResponseError:  # pragma: no cover - group/stream gone
        return 0
    # redis-py shape: [next_cursor, [(id, fields), ...], <deleted_ids?>]. Slice safely.
    messages = res[1] if isinstance(res, (list, tuple)) and len(res) >= 2 else []
    n = 0
    for mid, flds in messages:
        if not flds:  # tombstone → just clear from PEL
            await rdb.xack(ENRICH_STREAM, CONSUMER_GROUP, mid)
            continue
        await process_message(rdb, fetcher, mid, flds, stats, default_country=default_country)
        n += 1
    if n:
        log.info("enrich_worker reclaimed %d stranded PEL entries", n)
    return n


async def run(
    *,
    redis_url: str | None = None,
    fetcher: Fetcher | None = None,
    batch_size: int = 50,
    block_ms: int = 5_000,
    concurrency: int = 20,
    limit: int = 0,
    default_country: str = "",
    reclaim_idle_ms: int = RECLAIM_IDLE_MS,
) -> EnrichStats:
    """
    Consume ``stream:enrich_pending`` and bridge to ``stream:ingestion_raw``.

    ``limit`` > 0 enables the local "validate-with-a-limit-and-purge" mode: stop
    after ``limit`` payloads are emitted, and exit when the stream drains. With
    ``limit`` == 0 (VPS) it runs forever.
    """
    rdb = aioredis.from_url(redis_url or _REDIS_URL, decode_responses=True)
    if fetcher is None:
        fetcher = make_engine_fetcher()
    sem = asyncio.Semaphore(concurrency)
    stats = EnrichStats()
    consumer = f"{socket.gethostname()}:{os.getpid()}"

    await ensure_group(rdb, ENRICH_STREAM, CONSUMER_GROUP)
    log.info("enrich_worker start group=%s consumer=%s limit=%d", CONSUMER_GROUP, consumer, limit)
    try:
        while limit == 0 or stats.emitted < limit:
            # Durability: first reclaim any stranded PEL entries (un-ACKed by a
            # crashed/transient prior attempt), then read new messages.
            await reclaim_pending(
                rdb, fetcher, stats, consumer=consumer,
                idle_ms=reclaim_idle_ms, count=batch_size, default_country=default_country,
            )
            if limit and stats.emitted >= limit:
                break
            resp = await rdb.xreadgroup(
                CONSUMER_GROUP, consumer, {ENRICH_STREAM: ">"},
                count=batch_size, block=block_ms,
            )
            if not resp:
                if limit:  # local-limit mode: an empty read means the stream drained
                    break
                continue

            async def _guarded(mid: str, flds: dict) -> None:
                async with sem:
                    await process_message(
                        rdb, fetcher, mid, flds, stats, default_country=default_country
                    )

            for _stream, messages in resp:
                await asyncio.gather(*(_guarded(mid, flds) for mid, flds in messages))
                if limit and stats.emitted >= limit:
                    break
        log.info(
            "enrich_worker done emitted=%d dlq=%d transient=%d",
            stats.emitted, stats.dlq, stats.transient,
        )
        return stats
    finally:
        await rdb.aclose()


# ── production fetcher (anti-detection engine) ─────────────────────────────────
def make_engine_fetcher(
    *,
    engine_db_path: str | None = None,
    default_country: str = "",
    timeout: float = 25.0,
) -> Fetcher:
    """
    Build a ``Fetcher`` backed by the anti-detection engine (TLS/JA3 + identity).

    One curl_cffi session per (domain, country) is cached so the JA3 fingerprint
    stays coherent across a domain's listings, exactly as the coordinator does for
    the harvest path. The country comes from the pointer (``c``) via the
    ``_enrich_country`` ContextVar (``enrich_one`` sets it), falling back to
    ``default_country``. Direct (no-proxy) identities serve the T0/T1 portals that
    already populate ``vehicle_index``; a domain with no eligible identity raises
    so the message is treated as transient and retried later.
    """
    from urllib.parse import urlparse

    from scrapers.db import connect, migrate
    from scrapers.engine.antidetect import tls
    from scrapers.engine.identity import store as identity_store

    db_path = engine_db_path or os.environ.get("ENGINE_DB_PATH", "scrapers/engine.db")
    conn = connect(db_path)
    migrate(conn)
    sessions: dict[tuple[str, str], object] = {}

    def _domain(url: str) -> str:
        host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
        return host[4:] if host.startswith("www.") else host

    async def fetch(url: str) -> FetchResult:
        domain = _domain(url)
        country = _enrich_country.get() or default_country
        key = (domain, country)
        session = sessions.get(key)
        if session is None:
            identity = identity_store.pick_for_portal(
                conn, country, domain, min_trust=0.0, require_proxy=False
            )
            if identity is None:
                raise RuntimeError(f"no eligible identity for {domain}/{country}")
            session = tls.make_session(identity)
            sessions[key] = session
        resp = await session.get(url, timeout=timeout, allow_redirects=True)  # type: ignore[attr-defined]
        return FetchResult(
            url=str(getattr(resp, "url", url)),
            status_code=int(resp.status_code),
            body=resp.content or b"",
        )

    return fetch


def _build_config_from_env() -> dict:
    return {
        "redis_url": os.environ.get("REDIS_URL", _REDIS_URL),
        "batch_size": int(os.environ.get("ENRICH_BATCH_SIZE", "50")),
        "concurrency": int(os.environ.get("ENRICH_CONCURRENCY", "20")),
        "limit": int(os.environ.get("ENRICH_LIMIT", "0")),
        "default_country": os.environ.get("ENRICH_DEFAULT_COUNTRY", ""),
    }


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(**_build_config_from_env()))


if __name__ == "__main__":
    main()
