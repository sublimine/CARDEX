"""
Inventory Reaper — standalone microservice for listing lifecycle management.

Periodically scans ACTIVE vehicle listings in PostgreSQL and HEAD-checks their
source URLs. Dead listings (404/410) are marked as SOLD with a timestamp.

Runs independently from the Spider. The Spider ingests; the Reaper purges.

Usage:
    python -m inventory_reaper
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [reaper] %(message)s",
    force=True,
)
log = logging.getLogger("reaper")


async def main() -> None:
    from scrapers.inventory_reaper.reaper import InventoryReaper

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"
    )
    reaper = InventoryReaper(
        db_url=db_url,
        batch_size=int(os.environ.get("REAPER_BATCH_SIZE", "1000")),
        concurrency=int(os.environ.get("REAPER_CONCURRENCY", "50")),
        interval_minutes=int(os.environ.get("REAPER_INTERVAL_MINUTES", "60")),
    )

    try:
        await reaper.run_forever()
    except KeyboardInterrupt:
        log.info("reaper: interrupted")
    except Exception as exc:
        log.error("reaper: fatal — %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
