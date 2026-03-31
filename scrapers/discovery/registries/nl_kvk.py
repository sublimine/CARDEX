"""
KVK (Kamer van Koophandel) — Netherlands Chamber of Commerce open data.

All Dutch businesses are legally required to register with KVK.
Car dealers use SBI code 45.11 (Handel in en reparatie van personenauto's
en lichte bedrijfsauto's (geen import van nieuwe)) or 45.19.

Data access (two complementary approaches):

1. KVK Open Data (bulk CSV download):
   https://opendata.kvk.nl/datasets
   File: kvk-handelsregister-vestigingen.csv (~4M rows, updated weekly)
   Filter by sbi_code LIKE '45%'
   → Free, complete, offline processing

2. KVK API (per-lookup, rate limited, requires key):
   https://api.kvk.nl/test/api/v1/zoeken?sbiCode=4511
   → Used for enrichment/verification

We use approach 1 (bulk CSV) as primary — no rate limit, no key needed.
Fallback: approach 2 for targeted queries.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

# KVK open data bulk CSV URL (updated weekly by KVK)
_BULK_URL = "https://opendata.kvk.nl/bestanden/kvk-handelsregister-vestigingen.csv.gz"
# Fallback: search API (no auth for public endpoint in test mode)
_SEARCH_API = "https://api.kvk.nl/test/api/v1/zoeken"
_SBI_CODES = ["4511", "4519", "4520"]  # auto trade SBI codes
_PAGE_SIZE = 10


class NLKVKCrawler:
    """
    Downloads all Dutch car dealer establishments from KVK open data.
    Primary: bulk CSV download. Fallback: search API per SBI code.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:kvk_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:kvk_done", "1", ex=7 * 86400)

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("kvk: already done (within 7 days)")
            return

        # Try bulk CSV first
        total = 0
        async for dealer in self._crawl_bulk():
            total += 1
            yield dealer

        if total == 0:
            # Fallback to API
            async for dealer in self._crawl_api():
                total += 1
                yield dealer

        log.info("kvk: yielded %d NL dealers", total)
        if total > 0:
            await self._mark_done()

    async def _crawl_bulk(self) -> AsyncGenerator[dict, None]:
        """Download and parse KVK bulk CSV (gzipped)."""
        import gzip
        try:
            log.info("kvk: downloading bulk CSV from %s", _BULK_URL)
            async with self.session.get(
                _BULK_URL,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    log.warning("kvk bulk CSV: HTTP %d", resp.status)
                    return
                raw = await resp.read()

            decompressed = gzip.decompress(raw).decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(decompressed), delimiter=";")

            for row in reader:
                sbi = row.get("sbi_code_1", "")
                if not any(sbi.startswith(code) for code in _SBI_CODES):
                    continue
                if row.get("status_vestiging", "").lower() not in ("actief", "active", ""):
                    continue
                dealer = self._parse_csv_row(row)
                if dealer:
                    yield dealer

        except Exception as exc:
            log.warning("kvk bulk CSV failed: %s", exc)
            return

    async def _crawl_api(self) -> AsyncGenerator[dict, None]:
        """Fallback: paginate KVK search API per SBI code."""
        for sbi in _SBI_CODES:
            pagina = 1
            while True:
                params = {
                    "sbiCode": sbi,
                    "pagina": str(pagina),
                    "resultatenPerPagina": str(_PAGE_SIZE),
                }
                try:
                    async with self.session.get(
                        _SEARCH_API, params=params,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={"Accept": "application/json"},
                    ) as resp:
                        data = await resp.json()
                except Exception as exc:
                    log.warning("kvk api sbi=%s page=%d: %s", sbi, pagina, exc)
                    break

                items = data.get("resultaten") or []
                if not items:
                    break

                for item in items:
                    dealer = self._parse_api_item(item)
                    if dealer:
                        yield dealer

                total = data.get("totaal") or 0
                if pagina * _PAGE_SIZE >= total or len(items) < _PAGE_SIZE:
                    break

                pagina += 1
                await asyncio.sleep(0.5)

    @staticmethod
    def _parse_csv_row(row: dict) -> dict | None:
        try:
            name = row.get("naam_vestiging") or row.get("handelsnaam") or row.get("rechtsvorm_omschrijving")
            if not name:
                return None
            return {
                "source": "kvk",
                "registry_id": row.get("vestigingsnummer") or row.get("kvk_nummer"),
                "name": name.strip(),
                "country": "NL",
                "lat": None,  # bulk CSV doesn't include coords; enriched via geocoding
                "lng": None,
                "address": " ".join(filter(None, [
                    row.get("straatnaam"), row.get("huisnummer"), row.get("huisnummer_toevoeging"),
                ])),
                "city": row.get("plaatsnaam"),
                "postcode": row.get("postcode"),
                "sbi_code": row.get("sbi_code_1"),
                "website": row.get("website"),
                "phone": None,
                "status": "active",
                "raw": row,
            }
        except Exception:
            return None

    @staticmethod
    def _parse_api_item(item: dict) -> dict | None:
        try:
            adressen = item.get("adressen") or [{}]
            adres = adressen[0] if adressen else {}
            name = item.get("naam") or item.get("handelsnamen", [{}])[0].get("naam", "")
            if not name:
                return None
            return {
                "source": "kvk",
                "registry_id": item.get("vestigingsnummer") or item.get("kvkNummer"),
                "name": name.strip(),
                "country": "NL",
                "lat": None,
                "lng": None,
                "address": " ".join(filter(None, [
                    adres.get("straatnaam"), str(adres.get("huisnummer", "")),
                ])),
                "city": adres.get("plaats"),
                "postcode": adres.get("postcode"),
                "website": item.get("websites", [None])[0],
                "phone": None,
                "status": "active",
                "raw": item,
            }
        except Exception:
            return None
