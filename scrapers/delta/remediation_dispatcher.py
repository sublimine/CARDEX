"""Remediation dispatcher — the REAL call-site for the orphan remediate().

Consumes `stream:operator_events` and routes each alert by signal to an action.
This closes the gap the audit flagged: remediate() was complete + tested but had NO
production caller. Here it does.

Signal -> action map:
  volume_drift  -> remediate()  (re-detect config, re-scrape sample, revalidate)   [the orphan call-site]
  parse_fail    -> mark config drift for manual review (status=escalated)
  waf_block     -> mark requires-proxy / escalate (status=escalated, action recorded)
  timeout|dead  -> retry-with-backoff (status stays open until attempts exhausted)

Anti-churn (reuse of the P2 reclaim pattern): per-entity remediation attempts are capped
at MAX_REMEDIATIONS within a window; past the cap the alert is routed to stream:dlq and
status='dlq', so a permanently-broken entity can never livelock the remediator.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Awaitable, Callable

import asyncpg
import redis.asyncio as aioredis

from scrapers.dealer_scraping.remediation import remediate

log = logging.getLogger(__name__)

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
EVENTS_STREAM = "stream:operator_events"
GROUP = "cg_remediation"
DLQ_STREAM = "stream:dlq"
MAX_REMEDIATIONS = 3            # per-entity, within the recent window
WINDOW = "6 hours"
BLOCK_MS = 2000

DepsProvider = Callable[[], dict]
RemediateFn = Callable[..., Awaitable]


def make_deps_provider(pg: asyncpg.Pool, *, throwaway_redis_url: str | None = None) -> DepsProvider:
    """Production deps factory for remediate(), capturing the pool once.

    remediate() re-harvests a SAMPLE through the seam and PURGES it — it VALIDATES that a
    regenerated recipe yields inventory, it does NOT fill production. So the seam runs on a
    THROWAWAY redis (isolate=True, SEPARATE from this dispatcher's live stream redis, so the
    remediation re-harvest never touches in-flight work) and persists to the real PG for the
    ``recovered = persisted > 0`` check. Imports are lazy so importing the dispatcher stays
    cheap; the demo/tests inject fakes instead of calling this.
    """
    from scrapers.dealer_scraping.harvester import make_dealer_fetcher
    from scrapers.dealer_scraping.seam import make_live_purger, make_live_seam

    tw_url = throwaway_redis_url or os.environ.get("THROWAWAY_REDIS_URL", REDIS_URL)
    tw_rdb = aioredis.from_url(tw_url, decode_responses=False)
    static_fetcher = make_dealer_fetcher()
    # e07_fetcher=None: the headless dispatcher does not open Playwright per event (RAM); a
    # render-only dealer escalates rather than render-remediating here.
    seam_runner = make_live_seam(
        tw_rdb, static_fetcher, None, redis_url=tw_url, db_url=PG_DSN, isolate=True
    )
    purger = make_live_purger(pg)

    def provider() -> dict:
        return {"static_fetcher": static_fetcher, "e07_fetcher": None,
                "seam_runner": seam_runner, "purger": purger, "limit": 12}

    return provider


async def ensure_group(rdb: aioredis.Redis, stream: str, group: str) -> None:
    try:
        await rdb.xgroup_create(stream, group, id="0", mkstream=True)
        log.info("created group %s on %s", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _recent_remediations(pg: asyncpg.Connection, entity_ulid: str | None, source_key: str) -> int:
    """Recent re-scrape remediations for a source, keyed by source_key (always stored).

    entity_ulid is NULL in operator_alerts when the source has no source_entities row yet —
    the dominant case for freshly-discovered dealers (operator_events writes entity_ulid only
    when the row exists). Counting by entity_ulid alone returned 0 there, so MAX_REMEDIATIONS
    NEVER fired and a permanently-broken new dealer could livelock the remediator at scale.
    Match EITHER key so the anti-churn cap works for registered and unregistered sources alike.
    """
    return await pg.fetchval(
        f"""SELECT count(*) FROM operator_alerts
            WHERE (source_key = $2::text OR ($1::text IS NOT NULL AND entity_ulid = $1::text))
              AND remediation_action='re-scrape'
              AND updated_at > now() - interval '{WINDOW}'""",
        entity_ulid, source_key) or 0


async def _set_alert(pg, alert_id, *, status, action=None, result=None):
    await pg.execute(
        """UPDATE operator_alerts
           SET status=$2,
               remediation_action=COALESCE($3, remediation_action),
               remediation_result=COALESCE($4::jsonb, remediation_result),
               attempts=attempts+1, updated_at=now()
           WHERE alert_id=$1""",
        alert_id, status, action, json.dumps(result, default=str) if result is not None else None)


async def handle_event(
    pg: asyncpg.Connection, rdb: aioredis.Redis, f: dict[str, str], *,
    deps_provider: DepsProvider, remediate_fn: RemediateFn = remediate,
) -> dict:
    """Route one operator_event to its remediation action. Returns an evidence dict."""
    alert_id = int(f["alert_id"])
    entity_ulid = f.get("entity_ulid")
    source_key = f.get("source_key", "")
    signal = f.get("signal", "other")
    # entity country (for remediate); fall back to '' -> remediate upper-trims it
    country = await pg.fetchval("SELECT country FROM source_entities WHERE entity_ulid=$1", entity_ulid) or ""

    if signal == "volume_drift":
        attempts = await _recent_remediations(pg, entity_ulid, source_key)
        if attempts >= MAX_REMEDIATIONS:
            await rdb.xadd(DLQ_STREAM, {**f, "agent": "remediation_dispatcher", "reason": "max_remediations"})
            await _set_alert(pg, alert_id, status="dlq", action="re-scrape",
                             result={"reason": "anti_churn_cap", "attempts": attempts})
            return {"alert_id": alert_id, "action": "dlq", "attempts": attempts}
        await _set_alert(pg, alert_id, status="remediating", action="re-scrape")
        try:
            deps = deps_provider()
            res = await remediate_fn(source_key, country, **deps)
            result = {"recovered": res.recovered, "persisted": res.persisted,
                      "version": res.version, "new_strategy": res.new_strategy,
                      "strategy_changed": res.strategy_changed, "notes": list(res.notes)}
            await _set_alert(pg, alert_id, status="resolved" if res.recovered else "escalated",
                             action="re-scrape", result=result)
            return {"alert_id": alert_id, "action": "remediate", **result}
        except Exception as exc:  # noqa: BLE001 — never crash the dispatcher on one bad entity
            await _set_alert(pg, alert_id, status="escalated", action="re-scrape",
                             result={"error": str(exc)[:300]})
            log.exception("remediate failed for %s", source_key)
            return {"alert_id": alert_id, "action": "remediate_error", "error": str(exc)[:200]}

    if signal == "parse_fail":
        await _set_alert(pg, alert_id, status="escalated", action="config_review",
                         result={"hint": "regenerate config / inspect selectors"})
        return {"alert_id": alert_id, "action": "config_review"}

    if signal == "waf_block":
        await _set_alert(pg, alert_id, status="escalated", action="mark_requires_proxy",
                         result={"hint": "escalate tier / route via residential proxy"})
        return {"alert_id": alert_id, "action": "mark_requires_proxy"}

    # timeout | dead | other -> backoff retry (left open; resolved by next successful cycle)
    await _set_alert(pg, alert_id, status="open", action="retry_backoff")
    return {"alert_id": alert_id, "action": "retry_backoff"}


async def run(*, deps_provider: DepsProvider | None = None, oneshot: bool = False,
              max_idle_polls: int = 0) -> None:
    pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    # Build the production deps from the live pool when none is injected (the demo/tests inject).
    if deps_provider is None:
        deps_provider = make_deps_provider(pg)
    consumer = f"{socket.gethostname()}:{os.getpid()}"
    await ensure_group(rdb, EVENTS_STREAM, GROUP)
    log.info("remediation_dispatcher up consumer=%s", consumer)
    idle = 0
    try:
        while True:
            resp = await rdb.xreadgroup(GROUP, consumer, {EVENTS_STREAM: ">"}, count=10, block=BLOCK_MS)
            if not resp:
                idle += 1
                if oneshot or (max_idle_polls and idle >= max_idle_polls):
                    break
                continue
            idle = 0
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    f = {k.decode(): v.decode() for k, v in fields.items()}
                    async with pg.acquire() as conn:
                        try:
                            out = await handle_event(conn, rdb, f, deps_provider=deps_provider)
                            log.info("dispatched %s", out)
                        except Exception:  # noqa: BLE001
                            log.exception("dispatch error msg=%s", mid)
                    await rdb.xack(EVENTS_STREAM, GROUP, mid)
    finally:
        await rdb.aclose()
        await pg.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
