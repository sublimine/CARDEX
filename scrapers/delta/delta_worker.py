"""Delta ALWAYS-ON worker — turns the batch/dormant delta into a continuous stream.

Consumes `stream:harvest_batches` (one message = one entity's harvested URL set) and
applies it through the EXISTING delta primitives (indexer.insert_batch / delete_stale),
so every alta/baja lands in vehicle_index + vehicle_events — and therefore in the
per-entity API (/v1/entities/{ulid}/delta) — within milliseconds of the push, not in a
nightly batch.

Message fields (all strings, Redis stream):
  entity_ulid, source_key, country, domain, urls (JSON array), complete ('1'|'0')

  complete='1' => the urls are the FULL current set for (domain,country): apply SEEN for
                  new + GONE for vanished (insert_batch then delete_stale).
  complete='0' => incremental batch: SEEN only (no GONE — partial cycles never GONE-mark).

At-least-once: XACK on success; transient failure leaves the message pending and is
re-delivered via XAUTOCLAIM; a poison message past MAX_DELIVERIES goes to stream:dlq.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time

import asyncpg
import redis.asyncio as aioredis

from scrapers.common import indexer
from scrapers.delta import operator_events

log = logging.getLogger(__name__)

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
HARVEST_STREAM = "stream:harvest_batches"
GROUP = "cg_delta"
DLQ_STREAM = "stream:dlq"
MAX_DELIVERIES = 5
BLOCK_MS = 2000
RECLAIM_IDLE_MS = 60_000


async def ensure_group(rdb: aioredis.Redis, stream: str, group: str) -> None:
    try:
        await rdb.xgroup_create(stream, group, id="0", mkstream=True)
        log.info("created consumer group %s on %s", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def push_batch(rdb: aioredis.Redis, *, source_key: str, country: str, domain: str,
                     urls: list[str], complete: bool, entity_ulid: str | None = None) -> str:
    """Helper: enqueue one harvest batch. Returns the stream message id."""
    ent = entity_ulid or operator_events.entity_ulid_for(domain)
    return await rdb.xadd(HARVEST_STREAM, {
        "entity_ulid": ent, "source_key": source_key, "country": country, "domain": domain,
        "urls": json.dumps(urls), "complete": "1" if complete else "0",
    })


def _decode(fields: dict[bytes, bytes]) -> dict[str, str]:
    return {k.decode(): v.decode() for k, v in fields.items()}


async def _apply(pg: asyncpg.Pool, rdb: aioredis.Redis, f: dict[str, str]) -> dict:
    domain = f["domain"]
    country = f["country"]
    source_key = f.get("source_key", domain)
    urls = json.loads(f["urls"])
    complete = f.get("complete", "0") == "1"
    res = await indexer.insert_batch(pg, rdb, source_key, country, domain, urls)
    gone = 0
    if complete:
        gone = await indexer.delete_stale(pg, country, domain, res.seen)
    return {"new": res.new, "gone": gone, "seen": len(res.seen)}


async def _handle(pg: asyncpg.Pool, rdb: aioredis.Redis, msg_id: str, fields: dict[bytes, bytes]) -> None:
    f = _decode(fields)
    try:
        out = await _apply(pg, rdb, f)
        await rdb.xack(HARVEST_STREAM, GROUP, msg_id)
        log.info("delta applied id=%s domain=%s new=%d gone=%d", msg_id, f.get("domain"), out["new"], out["gone"])
    except Exception as exc:  # noqa: BLE001 — at-least-once: decide ack vs reclaim vs dlq
        pending = await rdb.xpending_range(HARVEST_STREAM, GROUP, min=msg_id, max=msg_id, count=1)
        deliveries = pending[0]["times_delivered"] if pending else 1
        if deliveries >= MAX_DELIVERIES:
            await rdb.xadd(DLQ_STREAM, {**f, "agent": "delta_worker", "reason": str(exc)[:300]})
            await rdb.xack(HARVEST_STREAM, GROUP, msg_id)
            log.error("delta poison id=%s -> DLQ after %d deliveries: %s", msg_id, deliveries, exc)
        else:
            log.warning("delta transient id=%s (delivery %d), will reclaim: %s", msg_id, deliveries, exc)
        try:
            await operator_events.emit_alert(
                source_key=f.get("source_key", f.get("domain", "?")), stage="seam",
                signal="parse_fail", severity="critical",
                evidence={"msg_id": msg_id, "error": str(exc)[:300], "deliveries": deliveries},
                pg=pg, rdb=rdb)
        except Exception:  # noqa: BLE001 — alerting must never crash the worker
            log.exception("failed to emit seam alert")


async def _reclaim(pg: asyncpg.Pool, rdb: aioredis.Redis, consumer: str) -> None:
    """Re-deliver messages stuck in another (crashed) consumer's PEL."""
    cursor = "0-0"
    while True:
        cursor, claimed, _ = await rdb.xautoclaim(
            HARVEST_STREAM, GROUP, consumer, min_idle_time=RECLAIM_IDLE_MS, start_id=cursor, count=20)
        for msg_id, fields in claimed:
            await _handle(pg, rdb, msg_id.decode() if isinstance(msg_id, bytes) else msg_id, fields)
        if cursor in ("0-0", b"0-0"):
            break


async def run(*, oneshot: bool = False, max_idle_polls: int = 0) -> None:
    pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    consumer = f"{socket.gethostname()}:{os.getpid()}"
    await ensure_group(rdb, HARVEST_STREAM, GROUP)
    log.info("delta_worker up consumer=%s stream=%s", consumer, HARVEST_STREAM)
    idle = 0
    try:
        while True:
            await _reclaim(pg, rdb, consumer)
            resp = await rdb.xreadgroup(GROUP, consumer, {HARVEST_STREAM: ">"}, count=10, block=BLOCK_MS)
            if not resp:
                idle += 1
                if oneshot or (max_idle_polls and idle >= max_idle_polls):
                    break
                continue
            idle = 0
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    await _handle(pg, rdb, mid, fields)
    finally:
        await rdb.aclose()
        await pg.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
