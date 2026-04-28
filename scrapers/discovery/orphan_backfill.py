"""
Orphan backfill — ingest Meili docs that have no corresponding vehicle_index row.

Image harvester + earlier loaders wrote docs to Meili without inserting a
matching vehicle_index row, so the enricher skips them. This script reads
every Meili doc, derives the url_hash from vehicle_ulid ('vi'+hash), and
upserts the missing rows into vehicle_index so the enricher covers them.
"""
from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [orphan_backfill] %(message)s",
)
log = logging.getLogger("orphan_backfill")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_BATCH = 1000

_HDR = {"Authorization": f"Bearer {_MEILI_KEY}"}


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    async with httpx.AsyncClient(timeout=120.0) as client:
        offset = 0
        total = 0
        inserted = 0
        while True:
            r = await client.get(
                f"{_MEILI_URL}/indexes/{_INDEX}/documents",
                headers=_HDR,
                params={"limit": _BATCH, "offset": offset,
                        "fields": "vehicle_ulid,source_url,source_country"},
            )
            if r.status_code != 200:
                log.error("meili GET %d: %s", r.status_code, r.text[:200])
                break
            results = r.json().get("results", [])
            if not results:
                break

            rows: list[tuple] = []
            for doc in results:
                ulid = doc.get("vehicle_ulid") or ""
                src = doc.get("source_url")
                cc = doc.get("source_country") or ""
                if not (ulid.startswith("vi") and src):
                    continue
                url_hash = ulid[2:]
                try:
                    dom = urlparse(src).netloc.lower().removeprefix("www.")
                except Exception:
                    dom = ""
                rows.append((url_hash, src, dom, cc))

            if rows:
                n = await pool.executemany(
                    """
                    INSERT INTO vehicle_index
                      (url_hash, url_original, source_domain, country, sitemap_source, last_seen)
                    VALUES ($1,$2,$3,$4,'orphan_backfill',NOW())
                    ON CONFLICT (url_hash) DO NOTHING
                    """,
                    rows,
                )
                inserted += len(rows)

            total += len(results)
            offset += len(results)
            if offset % 20000 == 0:
                log.info("scanned=%d inserted=%d", total, inserted)
            if len(results) < _BATCH:
                break

        log.info("DONE scanned=%d inserted=%d", total, inserted)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
