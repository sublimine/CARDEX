"""
Dealer Web Spider — orchestrator for extracting inventory from dealer websites.

Flow:
  1. Reads from stream:dealer_discovered (populated by DiscoveryOrchestrator)
  2. For each dealer with a website_url:
     a. Fetches homepage HTML
     b. DMSDetector fingerprints the platform (Autobiz / Autentia / Incadea / etc.)
     c. Routes to the appropriate DMS adapter
     d. Each adapter yields RawListing objects
     e. Listings are published to the standard pipeline via GatewayClient
     f. Dealer spider_status updated in PostgreSQL (DONE / FAILED / NO_INVENTORY)

Concurrency model:
  - SPIDER_CONCURRENCY workers (default 20) process dealers in parallel
  - Each worker has its own aiohttp session and rate limiter
  - Bloom filter (bloom:dealer_place_ids) prevents re-crawling the same dealer
    within the TTL window (7 days)

Re-crawl strategy:
  - Dealers with spider_status=DONE are re-queued after 7 days
  - Dealers with spider_status=FAILED are retried after 24h (up to 3 attempts)
  - Dealers with NO_INVENTORY are checked weekly (website may add stock)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncGenerator

import aiohttp
import asyncpg
from redis.asyncio import from_url as redis_from_url

from scrapers.common.gateway_client import GatewayClient
from scrapers.common.models import RawListing
from scrapers.dealer_spider.detector import DMSDetector
from scrapers.dealer_spider.dms import (
    autobiz,
    autentia,
    incadea,
    motormanager,
    wp_car_manager,
)
from scrapers.dealer_spider.dms import generic_feed, schema_org, generic_html

log = logging.getLogger(__name__)

_STREAM_IN  = "stream:dealer_discovered"
_CG_SPIDER  = "cg_dealer_spider"
_CONCURRENCY = int(os.environ.get("SPIDER_CONCURRENCY", "20"))
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)

# Maps DMS platform string → extractor coroutine
_DMS_EXTRACTORS = {
    "autobiz":       autobiz.extract,
    "autentia":      autentia.extract,
    "incadea":       incadea.extract,
    "motormanager":  motormanager.extract,
    "wp_car_manager": wp_car_manager.extract,
    "dealer_inspire": generic_feed.extract,  # Dealer Inspire exposes standard JSON feeds
    "dealersocket":   generic_feed.extract,
    "automanager":    generic_feed.extract,
    "generic_feed":   generic_feed.extract,
    "schema_org":     schema_org.extract,
    "generic_html":   generic_html.extract,
}

_HEADERS = {
    "User-Agent": (
        "CardexBot/1.0 (+https://cardex.eu/bot; scraping@cardex.eu) "
        "aiohttp/3.9 Python/3.12"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}


# ── HTTP helpers shared across workers ───────────────────────────────────────

class _HTTPHelper:
    """Thin async HTTP helper injected into DMS adapters."""

    def __init__(self, session: aiohttp.ClientSession):
        self._s = session

    async def get_json(self, url: str, **kwargs) -> dict | list:
        async with self._s.get(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def post_json(self, url: str, **kwargs) -> dict | list:
        async with self._s.post(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def get_text(self, url: str, **kwargs) -> str:
        async with self._s.get(url, timeout=_REQUEST_TIMEOUT, **kwargs) as r:
            r.raise_for_status()
            return await r.text()

    async def head_ok(self, url: str) -> bool:
        try:
            async with self._s.head(
                url, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True,
            ) as r:
                return r.status < 400
        except Exception:
            return False


# ── Spider worker ─────────────────────────────────────────────────────────────

async def _process_dealer(
    msg_id: str,
    fields: dict,
    session: aiohttp.ClientSession,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """Process a single dealer: detect DMS, extract inventory, publish listings."""
    dealer_id = fields.get("dealer_id", "")
    name      = fields.get("name", "unknown")
    country   = fields.get("country", "")
    website   = fields.get("website", "").strip()

    if not website or not website.startswith("http"):
        await _update_spider_status(pg, dealer_id, "NO_INVENTORY", "no_website")
        return

    # Bloom: skip if crawled recently
    bloom_key = f"dealer:crawled:{dealer_id}"
    if await rdb.exists(bloom_key):
        log.debug("spider: skip %s (bloom hit)", name)
        return

    http = _HTTPHelper(session)
    detector = DMSDetector(http)

    # 1. Fetch homepage
    try:
        async with session.get(
            website, timeout=_REQUEST_TIMEOUT, headers=_HEADERS, allow_redirects=True,
        ) as resp:
            if resp.status >= 400:
                log.warning("spider: %s homepage HTTP %d", name, resp.status)
                await _update_spider_status(pg, dealer_id, "FAILED", f"http_{resp.status}")
                return
            html = await resp.text(errors="replace")
            # Use final URL after redirects as canonical base
            base_url = str(resp.url).rstrip("/")
    except Exception as exc:
        log.warning("spider: %s homepage fetch failed: %s", name, exc)
        await _update_spider_status(pg, dealer_id, "FAILED", str(exc)[:120])
        return

    # 2. Detect DMS platform
    platform, feed_url = await detector.detect(base_url, html)
    log.info("spider: %s (%s) → platform=%s", name, country, platform)

    # 3. Route to DMS extractor
    extractor = _DMS_EXTRACTORS.get(platform)
    if not extractor:
        log.warning("spider: no extractor for platform=%s dealer=%s", platform, name)
        await _update_spider_status(pg, dealer_id, "NO_INVENTORY", f"no_extractor:{platform}")
        return

    # 4. Extract listings
    listing_count = 0
    error_count   = 0
    try:
        async for listing in extractor(
            http=http,
            dealer_id=dealer_id,
            dealer_name=name,
            base_url=feed_url or base_url,
            country=country,
        ):
            try:
                await gateway.ingest(listing)
                listing_count += 1
            except Exception as exc:
                error_count += 1
                log.debug("spider: ingest error %s: %s", name, exc)
    except Exception as exc:
        log.warning("spider: extraction failed %s (platform=%s): %s", name, platform, exc)
        await _update_spider_status(pg, dealer_id, "FAILED", str(exc)[:120])
        return

    # 5. Update dealer record
    status = "DONE" if listing_count > 0 else "NO_INVENTORY"
    await _update_spider_status(pg, dealer_id, status, platform, listing_count)

    # 6. Mark as crawled in bloom (7-day TTL)
    await rdb.set(bloom_key, "1", ex=7 * 86400)

    log.info(
        "spider: %s done — platform=%s listings=%d errors=%d",
        name, platform, listing_count, error_count,
    )


async def _update_spider_status(
    pg: asyncpg.Pool,
    dealer_id: str,
    status: str,
    dms_or_reason: str = "",
    listing_count: int = 0,
) -> None:
    try:
        await pg.execute("""
            UPDATE dealers
            SET spider_status       = $1,
                spider_last_run     = now(),
                spider_dms          = $2,
                spider_listing_count = $3,
                updated_at          = now()
            WHERE place_id = $4
               OR registry_id = $4
               OR osm_id = $4
        """, status, dms_or_reason[:64], listing_count, dealer_id)
    except Exception as exc:
        log.warning("spider: db update failed dealer_id=%s: %s", dealer_id, exc)


# ── Consumer loop ─────────────────────────────────────────────────────────────

async def _consumer(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    pg: asyncpg.Pool,
    rdb,
    gateway: GatewayClient,
) -> None:
    """Long-running consumer that reads from the Redis stream."""
    conn_headers = {
        **_HEADERS,
        "Connection": "keep-alive",
    }
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        headers=conn_headers,
        connector=connector,
        trust_env=True,
    ) as session:
        last_id = ">"   # read only new messages
        while True:
            try:
                entries = await rdb.xreadgroup(
                    groupname=_CG_SPIDER,
                    consumername=f"spider-worker-{worker_id}",
                    streams={_STREAM_IN: last_id},
                    count=1,
                    block=5000,   # 5s block
                )
            except Exception as exc:
                log.warning("spider worker %d: xreadgroup error: %s", worker_id, exc)
                await asyncio.sleep(2)
                continue

            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    async with semaphore:
                        try:
                            await _process_dealer(
                                msg_id, fields, session, pg, rdb, gateway,
                            )
                        except Exception as exc:
                            log.error("spider worker %d: unhandled error: %s", worker_id, exc)
                        finally:
                            # Always ACK — failures are tracked in DB, not re-queued
                            try:
                                await rdb.xack(_STREAM_IN, _CG_SPIDER, msg_id)
                            except Exception:
                                pass


# ── Bootstrap ─────────────────────────────────────────────────────────────────

async def _ensure_consumer_group(rdb) -> None:
    """Create the consumer group if it doesn't exist."""
    try:
        await rdb.xgroup_create(_STREAM_IN, _CG_SPIDER, id="0", mkstream=True)
        log.info("spider: created consumer group %s", _CG_SPIDER)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            pass  # already exists
        else:
            log.warning("spider: xgroup_create warning: %s", exc)


async def run() -> None:
    """Entry point for run_scraper.py target 'dealer_spider'."""
    import signal
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [spider] %(message)s",
    )

    rdb = redis_from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    pg  = await asyncpg.create_pool(
        os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"),
        min_size=2, max_size=8,
    )
    gateway = GatewayClient()

    await _ensure_consumer_group(rdb)

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    stop_event = asyncio.Event()

    def _handle_signal(*_):
        log.info("spider: shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT,  _handle_signal)
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)

    log.info("spider: starting %d workers (concurrency=%d)", _CONCURRENCY, _CONCURRENCY)

    workers = [
        asyncio.create_task(_consumer(i, semaphore, pg, rdb, gateway))
        for i in range(_CONCURRENCY)
    ]

    await stop_event.wait()

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    await pg.close()
    await rdb.aclose()
    await gateway.close()
    log.info("spider: shutdown complete")
