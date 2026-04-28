"""
Quality gate — delete any Meili doc that does not satisfy 100% completeness.

Required fields per doc (ALL must be present and non-empty):
    make, model, price_eur, thumbnail_url, description, year, mileage_km

Docs that fail are:
  - Deleted from Meili by vehicle_ulid
  - Deleted from vehicle_index by url_hash (derived from ulid → drop 'vi' prefix)
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [quality_gate] %(message)s",
)
log = logging.getLogger("quality_gate")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_BATCH = int(os.environ.get("QG_BATCH", "1000"))
_REQUIRED = ("make", "model", "price_eur", "thumbnail_url", "description", "year", "mileage_km")

_HDR = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}


def _is_complete(doc: dict) -> bool:
    for k in _REQUIRED:
        v = doc.get(k)
        if v is None or v == "" or v == 0:
            return False
    return True


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    async with httpx.AsyncClient(timeout=120.0) as client:
        offset = 0
        kept = 0
        deleted = 0
        to_delete_ulids: list[str] = []
        to_delete_hashes: list[str] = []

        while True:
            r = await client.get(
                f"{_MEILI_URL}/indexes/{_INDEX}/documents",
                headers=_HDR,
                params={"limit": _BATCH, "offset": offset,
                        "fields": "vehicle_ulid," + ",".join(_REQUIRED)},
            )
            if r.status_code != 200:
                log.error("meili GET %d: %s", r.status_code, r.text[:200])
                break
            data = r.json()
            results = data.get("results", [])
            if not results:
                break

            for doc in results:
                if _is_complete(doc):
                    kept += 1
                else:
                    ulid = doc.get("vehicle_ulid")
                    if ulid:
                        to_delete_ulids.append(ulid)
                        if ulid.startswith("vi"):
                            to_delete_hashes.append(ulid[2:])
                    deleted += 1

            if len(to_delete_ulids) >= 5000:
                await _flush(client, pool, to_delete_ulids, to_delete_hashes)
                to_delete_ulids.clear()
                to_delete_hashes.clear()

            offset += len(results)
            if offset % 10000 == 0:
                log.info("scanned=%d kept=%d deleted=%d", offset, kept, deleted)
            if len(results) < _BATCH:
                break

        if to_delete_ulids:
            await _flush(client, pool, to_delete_ulids, to_delete_hashes)

        log.info("DONE scanned=%d kept=%d deleted=%d", offset, kept, deleted)

    await pool.close()


async def _flush(
    client: httpx.AsyncClient,
    pool: asyncpg.Pool,
    ulids: list[str],
    hashes: list[str],
) -> None:
    r = await client.post(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents/delete-batch",
        headers=_HDR,
        json=ulids,
    )
    if r.status_code not in (200, 202):
        log.warning("meili delete %d: %s", r.status_code, r.text[:200])
    if hashes:
        await pool.execute(
            "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])",
            hashes,
        )
    log.info("flushed %d ulids", len(ulids))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
