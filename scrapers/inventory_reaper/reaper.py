"""
Inventory Reaper — async batch URL health checker.

Architecture:
  1. Reads batches of 1000 ACTIVE vehicle URLs from PostgreSQL
  2. HEAD-checks each URL with bounded concurrency (default 50)
  3. Marks 404/410 responses as SOLD with sold_at timestamp
  4. Skips URLs checked within the last 24h (via last_updated_at)
  5. Runs on a configurable interval (default 60 minutes)

Separation of concerns:
  - Spider: ingests new listings (write path)
  - Reaper: validates existing listings (lifecycle path)
  - These two NEVER share execution context
"""
from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
import asyncpg

log = logging.getLogger("reaper")

_HEADERS = {
    "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot) HealthCheck",
    "Accept": "*/*",
}


class InventoryReaper:
    def __init__(
        self,
        db_url: str,
        batch_size: int = 1000,
        concurrency: int = 50,
        interval_minutes: int = 60,
    ):
        self._db_url = db_url
        self._batch_size = batch_size
        self._concurrency = concurrency
        self._interval_seconds = interval_minutes * 60

    async def run_forever(self) -> None:
        """Main loop: reap → sleep → repeat."""
        self._pg = await asyncpg.create_pool(self._db_url, min_size=2, max_size=8)
        log.info(
            "reaper: started — batch=%d concurrency=%d interval=%dm",
            self._batch_size, self._concurrency, self._interval_seconds // 60,
        )

        try:
            while True:
                await self._reap_cycle()
                log.info("reaper: sleeping %d minutes", self._interval_seconds // 60)
                await asyncio.sleep(self._interval_seconds)
        finally:
            await self._pg.close()

    async def _reap_cycle(self) -> None:
        """One full reaping pass over all ACTIVE listings."""
        t0 = time.monotonic()
        total_checked = 0
        total_sold = 0
        total_errors = 0

        connector = aiohttp.TCPConnector(
            limit=self._concurrency,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=10, connect=5)

        async with aiohttp.ClientSession(
            headers=_HEADERS,
            connector=connector,
            timeout=timeout,
        ) as session:
            offset = 0
            while True:
                # Fetch batch of URLs not checked in the last 24h
                rows = await self._pg.fetch("""
                    SELECT vehicle_ulid, source_url
                    FROM vehicles
                    WHERE listing_status = 'ACTIVE'
                      AND source_url IS NOT NULL
                      AND (last_updated_at IS NULL
                           OR last_updated_at < now() - interval '24 hours')
                    ORDER BY last_updated_at ASC NULLS FIRST
                    LIMIT $1 OFFSET $2
                """, self._batch_size, offset)

                if not rows:
                    break

                # Check batch with bounded concurrency
                semaphore = asyncio.Semaphore(self._concurrency)
                results = await asyncio.gather(*[
                    self._check_url(session, semaphore, row["vehicle_ulid"], row["source_url"])
                    for row in rows
                ])

                batch_sold = 0
                batch_errors = 0
                for status in results:
                    if status == "SOLD":
                        batch_sold += 1
                    elif status == "ERROR":
                        batch_errors += 1

                total_checked += len(rows)
                total_sold += batch_sold
                total_errors += batch_errors

                log.info(
                    "reaper: batch — checked=%d, sold=%d, errors=%d (cumulative: %d/%d/%d)",
                    len(rows), batch_sold, batch_errors,
                    total_checked, total_sold, total_errors,
                )

                # If batch was full, there are more
                if len(rows) < self._batch_size:
                    break
                offset += self._batch_size

        elapsed = time.monotonic() - t0
        print(
            f"[REAPER] cycle complete: {total_checked} checked, "
            f"{total_sold} marked SOLD, {total_errors} errors, "
            f"{elapsed:.1f}s elapsed",
            flush=True,
        )

    async def _check_url(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        vehicle_ulid: str,
        source_url: str,
    ) -> str:
        """HEAD-check a single URL. Returns 'ALIVE', 'SOLD', or 'ERROR'."""
        async with semaphore:
            try:
                async with session.head(
                    source_url, allow_redirects=True,
                ) as resp:
                    if resp.status in (404, 410):
                        await self._mark_sold(vehicle_ulid)
                        return "SOLD"
                    else:
                        # Touch last_updated_at so we don't re-check for 24h
                        await self._pg.execute(
                            "UPDATE vehicles SET last_updated_at = now() WHERE vehicle_ulid = $1",
                            vehicle_ulid,
                        )
                        return "ALIVE"
            except (aiohttp.ClientError, asyncio.TimeoutError):
                # Network error — don't mark as sold, just skip
                return "ERROR"
            except Exception as exc:
                log.debug("reaper: unexpected error for %s: %s", source_url, exc)
                return "ERROR"

    async def _mark_sold(self, vehicle_ulid: str) -> None:
        """Mark a vehicle listing as SOLD."""
        try:
            await self._pg.execute("""
                UPDATE vehicles
                SET listing_status = 'SOLD',
                    sold_at = now(),
                    last_updated_at = now()
                WHERE vehicle_ulid = $1
                  AND listing_status = 'ACTIVE'
            """, vehicle_ulid)
        except Exception as exc:
            log.warning("reaper: failed to mark %s as SOLD: %s", vehicle_ulid, exc)
