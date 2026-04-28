"""
Quality sampler — fetches 100 random Meili docs and computes a quality score
per field. Read-only validation.
"""
from __future__ import annotations

import asyncio
import json
import os
import random

import httpx

_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_HDR = {"Authorization": f"Bearer {_MEILI_KEY}", "Content-Type": "application/json"}

_FIELDS = [
    "make", "model", "variant", "price_eur", "year",
    "mileage_km", "thumbnail_url", "description",
    "fuel_type", "transmission", "source_country",
    "source_url", "power_kw", "power_hp", "vin",
]


async def run() -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{_MEILI_URL}/indexes/{_INDEX}/stats", headers=_HDR)
        total = r.json().get("numberOfDocuments", 0)

        sample_size = 500
        offsets = sorted(random.sample(range(total), min(sample_size, total)))
        docs = []
        for off in offsets:
            r = await client.get(
                f"{_MEILI_URL}/indexes/{_INDEX}/documents",
                headers=_HDR,
                params={"limit": 1, "offset": off, "fields": ",".join(_FIELDS)},
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    docs.append(results[0])

        if not docs:
            print("No docs sampled")
            return

        counts: dict = {f: 0 for f in _FIELDS}
        for d in docs:
            for f in _FIELDS:
                v = d.get(f)
                if v is not None and v != "" and v != 0 and v != []:
                    counts[f] += 1

        print(f"Sample size: {len(docs)} / {total}")
        print(f"Field fill rates:")
        for f in _FIELDS:
            pct = 100 * counts[f] / len(docs)
            bar = "#" * int(pct / 5)
            print(f"  {f:16} {counts[f]:4}/{len(docs)} ({pct:5.1f}%) {bar}")

        complete_all = sum(
            1 for d in docs
            if all(d.get(f) for f in ("make", "model", "price_eur", "year", "mileage_km"))
        )
        print(f"\nAll 5 critical: {complete_all}/{len(docs)} ({100*complete_all/len(docs):.1f}%)")

        complete_full = sum(
            1 for d in docs
            if all(d.get(f) for f in ("make", "model", "price_eur", "year",
                                       "mileage_km", "thumbnail_url",
                                       "description", "fuel_type", "transmission"))
        )
        print(f"All 9 full:     {complete_full}/{len(docs)} ({100*complete_full/len(docs):.1f}%)")


if __name__ == "__main__":
    asyncio.run(run())
