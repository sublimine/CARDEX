"""
SIRENE standalone runner — pulls all FR car dealer establishments
partitioned by department × NAF code and writes to discovery_candidates
as identity rows (no domain). A later pass resolves name → domain.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

from scrapers.discovery.sources.fr_sirene import SireneSource

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [sirene] %(message)s",
)
log = logging.getLogger("sirene")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    written = 0
    seen = 0
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        src = SireneSource(client)
        async for cand in src.discover("FR"):
            seen += 1
            try:
                await pool.execute(
                    """
                    INSERT INTO discovery_candidates
                      (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                    ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
                    DO NOTHING
                    """,
                    cand.get("domain"),
                    cand.get("country"),
                    cand.get("source_layer"),
                    cand.get("source"),
                    cand.get("url"),
                    cand.get("name"),
                    cand.get("address"),
                    cand.get("city"),
                    cand.get("postcode"),
                    cand.get("phone"),
                    cand.get("email"),
                    cand.get("lat"),
                    cand.get("lng"),
                    cand.get("registry_id"),
                    json.dumps(cand.get("external_refs") or {}),
                )
                written += 1
                if seen % 500 == 0:
                    log.info("sirene progress: seen=%d written=%d", seen, written)
            except Exception as exc:
                log.debug("upsert %s: %s", cand.get("registry_id"), exc)
    log.info("DONE seen=%d written=%d", seen, written)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
