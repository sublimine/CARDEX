"""
Quality audit — cold report on completeness of Meili docs.
No writes. Prints a JSON breakdown by country × field.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx

_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_HDR = {"Authorization": f"Bearer {_MEILI_KEY}", "Content-Type": "application/json"}

_COUNTRIES = ("DE", "FR", "ES", "NL", "BE", "CH")
_FIELDS = ("make", "model", "variant", "price_eur", "year",
           "mileage_km", "thumbnail_url", "description",
           "fuel_type", "transmission")


async def _count(client: httpx.AsyncClient, filter_expr: str) -> int:
    r = await client.post(
        f"{_MEILI_URL}/indexes/{_INDEX}/search",
        headers=_HDR,
        json={"q": "", "limit": 0, "filter": filter_expr},
    )
    if r.status_code != 200:
        return -1
    return r.json().get("estimatedTotalHits", 0)


async def run() -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        stats = await client.get(f"{_MEILI_URL}/indexes/{_INDEX}/stats", headers=_HDR)
        total = stats.json().get("numberOfDocuments", 0)

        report: dict = {
            "total": total,
            "by_country": {},
            "complete_all_critical": 0,
        }

        # Filterable fields only — thumbnail_url and description are NOT filterable
        # in the current Meili config. We use make/model/price/year/mileage as proxy.
        critical = "make EXISTS AND model EXISTS AND price_eur EXISTS AND year EXISTS AND mileage_km EXISTS"
        report["complete_all_critical"] = await _count(client, critical)

        for country in _COUNTRIES:
            country_total = await _count(client, f"source_country = {country}")
            row = {"total": country_total}
            for field in ("make", "model", "price_eur", "year", "mileage_km",
                          "fuel_type", "transmission"):
                row[field] = await _count(client, f"source_country = {country} AND {field} EXISTS")
            row["all_5_critical"] = await _count(
                client, f"source_country = {country} AND {critical}",
            )
            report["by_country"][country] = row

        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
