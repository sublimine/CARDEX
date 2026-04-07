"""
Search Indexer — PostgreSQL → MeiliSearch watermark-based sync.

Polls PostgreSQL every 60s for vehicles with last_updated_at > watermark.
Transforms rows into flat search documents and pushes in 1000-doc batches.
Watermark persisted in Redis for crash recovery.

Usage:
    python -m search_indexer
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [indexer] %(message)s",
    force=True,
)

async def main() -> None:
    from scrapers.search_indexer.indexer import SearchIndexer

    indexer = SearchIndexer(
        db_url=os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
        meili_url=os.environ.get("MEILI_URL", "http://localhost:7700"),
        meili_key=os.environ.get("MEILI_MASTER_KEY", ""),
        poll_interval=int(os.environ.get("INDEXER_POLL_INTERVAL", "60")),
        batch_size=int(os.environ.get("INDEXER_BATCH_SIZE", "1000")),
    )

    try:
        await indexer.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.getLogger("indexer").error("fatal: %s", exc, exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
