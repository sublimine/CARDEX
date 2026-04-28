"""
source_country backfill — derives country from source_url TLD for every
Meili doc that lacks it. Makes the country filter functional across
the entire corpus.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [country] %(message)s",
)
log = logging.getLogger("country")

_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_BATCH = int(os.environ.get("CB_BATCH", "1000"))
_HDR = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}

_TLD_COUNTRY = {
    "de": "DE", "at": "DE",  # AT folded into DE (same market)
    "fr": "FR",
    "es": "ES",
    "nl": "NL",
    "be": "BE",
    "ch": "CH",
}


def _country_from_url(url: str) -> str | None:
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return None
    if not net:
        return None
    if net.startswith("www."):
        net = net[4:]
    tld = net.split(".")[-1] if "." in net else ""
    return _TLD_COUNTRY.get(tld)


async def run() -> None:
    async with httpx.AsyncClient(timeout=120.0) as client:
        offset = 0
        updated = 0
        scanned = 0
        unchanged = 0
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
            docs = r.json().get("results", [])
            if not docs:
                break

            batch_updates: list[dict] = []
            for doc in docs:
                scanned += 1
                if doc.get("source_country"):
                    unchanged += 1
                    continue
                src = doc.get("source_url")
                if not src:
                    continue
                country = _country_from_url(src)
                if not country:
                    continue
                batch_updates.append({
                    "vehicle_ulid": doc["vehicle_ulid"],
                    "source_country": country,
                })

            if batch_updates:
                r2 = await client.put(
                    f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
                    headers=_HDR,
                    json=batch_updates,
                )
                if r2.status_code in (200, 201, 202):
                    updated += len(batch_updates)
                else:
                    log.warning("meili PUT %d: %s", r2.status_code, r2.text[:200])

            offset += len(docs)
            if offset % 10000 == 0:
                log.info("scanned=%d updated=%d unchanged=%d", scanned, updated, unchanged)
            if len(docs) < _BATCH:
                break

        log.info("DONE scanned=%d updated=%d unchanged=%d", scanned, updated, unchanged)


if __name__ == "__main__":
    asyncio.run(run())
