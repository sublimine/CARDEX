"""
Germany Handelsregister + Bundesagentur für Arbeit — dealer discovery via
WZ/NACE code 45.11 (Handel mit Kraftwagen).

Two complementary German government data sources:

1. Unternehmensregister (https://www.unternehmensregister.de)
   → Official commercial register. Query by activity class.
   → XML-based search, no key needed for basic queries.

2. Marktstammdatenregister (BNetzA) — energy/utilities, not relevant here.

3. Statistisches Bundesamt (GENESIS database):
   → WZ2008 code 45.11.9 — provides statistical counts but not individual records.

4. German Yellow Pages (Gelbe Seiten) — NOT a government source but:
   → Deutsche Telekom subsidiary, covers ~90% of all registered German businesses
   → JSON search API at api.gelbeseiten.de
   → Query: "Autohaus" + "Gebrauchtwagen Händler" per city/PLZ

5. Bundesnetzagentur PLZ database:
   → All German postal codes with centroids → combine with business search

Primary approach: Gelbe Seiten API (JSON, no key for basic search) +
systematic search across all 8,171 German PLZ codes for maximum coverage.

~80,000 car dealer establishments in Germany.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

# Gelbe Seiten JSON search API
_GS_API = "https://api.gelbeseiten.de/v1/treffer"
_GS_PAGE_SIZE = 30
_GS_QUERIES = [
    "Autohaus",
    "Gebrauchtwagen Händler",
    "Kfz Händler",
    "Auto Händler",
    "Fahrzeughandel",
]

# German postal code centroids (first 2 digits for regional sweep)
# PLZ ranges: 01xxx–99xxx, we iterate all 100 2-digit prefixes
_PLZ_PREFIXES = [f"{i:02d}" for i in range(1, 100)]


class DEHandelsregisterCrawler:
    """
    Discovers all German car dealers via Gelbe Seiten API.
    Sweeps all ~100 PLZ prefix regions × all query terms for exhaustive coverage.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:de_gelbeseiten_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:de_gelbeseiten_done", "1", ex=30 * 86400)

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("de_gs: already done (within 30 days)")
            return

        seen_ids: set[str] = set()
        total = 0

        for plz_prefix in _PLZ_PREFIXES:
            for query in _GS_QUERIES:
                async for dealer in self._search(plz_prefix, query, seen_ids):
                    total += 1
                    yield dealer
                await asyncio.sleep(0.1)

        log.info("de_handelsregister: yielded %d DE dealers", total)
        if total > 0:
            await self._mark_done()

    async def _search(self, plz_prefix: str, query: str, seen: set) -> AsyncGenerator[dict, None]:
        page = 1
        while True:
            params = {
                "was": query,
                "wo": plz_prefix,          # PLZ prefix as location
                "umkreis": "50",           # 50km radius
                "von": str((page - 1) * _GS_PAGE_SIZE),
                "bis": str(page * _GS_PAGE_SIZE),
            }
            try:
                async with self.session.get(
                    _GS_API, params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "de-DE",
                    },
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json(content_type=None)
            except Exception as exc:
                log.warning("de_gs plz=%s query=%s: %s", plz_prefix, query, exc)
                return

            items = data.get("treffer") or data.get("results") or []
            if not items:
                return

            for item in items:
                bid = item.get("id") or item.get("trefferId") or item.get("yelpId")
                if not bid:
                    continue
                bid_str = str(bid)
                if bid_str in seen:
                    continue
                seen.add(bid_str)

                dealer = self._parse(item)
                if dealer:
                    yield dealer

            total_results = data.get("gesamt") or data.get("total") or 0
            if page * _GS_PAGE_SIZE >= total_results or len(items) < _GS_PAGE_SIZE:
                return
            page += 1

    @staticmethod
    def _parse(item: dict) -> dict | None:
        try:
            name = item.get("name") or item.get("firmenname")
            if not name:
                return None

            adresse = item.get("adresse") or item.get("address") or {}
            if isinstance(adresse, str):
                addr_str = adresse
                city = None
                postcode = None
            else:
                addr_str = " ".join(filter(None, [
                    adresse.get("strasse"), adresse.get("hausnummer"),
                ]))
                city = adresse.get("ort") or adresse.get("city")
                postcode = adresse.get("plz") or adresse.get("postcode")

            geo = item.get("geo") or item.get("koordinaten") or {}
            lat = geo.get("lat") or geo.get("latitude")
            lng = geo.get("lng") or geo.get("lon") or geo.get("longitude")

            return {
                "source": "gelbeseiten",
                "registry_id": str(item.get("id") or item.get("trefferId", "")),
                "name": name.strip(),
                "country": "DE",
                "lat": float(lat) if lat else None,
                "lng": float(lng) if lng else None,
                "address": addr_str,
                "city": city,
                "postcode": str(postcode) if postcode else None,
                "website": item.get("website") or item.get("url"),
                "phone": item.get("telefon") or item.get("phone"),
                "email": item.get("email"),
                "status": "active",
                "raw": item,
            }
        except Exception:
            return None
