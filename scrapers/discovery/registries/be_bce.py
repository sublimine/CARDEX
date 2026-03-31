"""
BCE (Banque Carrefour des Entreprises) — Belgium's official business registry.

All Belgian businesses are registered in the BCE (French) / KBO (Dutch).
Car dealers use NACE code 4511 (Handel in personenwagens en lichte bedrijfswagens).

Data access:
  Open Data portal: https://economie.fgov.be/fr/themes/entreprises/banque-carrefour-des-entreprises/open-data-bce
  → Full CSV download (updated monthly), no authentication required
  → Contains all enterprises + establishments with NACE codes, addresses, status

  API (free public):
  GET https://kbopub.economie.fgov.be/kbopub/searchWordForm.action
  + AJAX JSON endpoint for programmatic access

~20,000 active car dealer establishments in Belgium.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

# BCE open data ZIP download (updated monthly)
_BULK_URL = "https://kbopub.economie.fgov.be/kbo-open-data/affiliation/zip/latest/KboOpenData.zip"
# Fallback search API
_SEARCH_API = "https://kbopub.economie.fgov.be/kbopub/zoeknaamfonetischform.json"
_NACE_CODES = ["4511", "4519", "4520"]


class BEBCECrawler:
    """
    Downloads all Belgian car dealer establishments from BCE open data.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:bce_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:bce_done", "1", ex=30 * 86400)

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("bce: already done (within 30 days)")
            return

        total = 0
        async for dealer in self._crawl_bulk():
            total += 1
            yield dealer

        if total == 0:
            async for dealer in self._crawl_search_api():
                total += 1
                yield dealer

        log.info("bce: yielded %d BE dealers", total)
        if total > 0:
            await self._mark_done()

    async def _crawl_bulk(self) -> AsyncGenerator[dict, None]:
        try:
            log.info("bce: downloading open data ZIP…")
            async with self.session.get(
                _BULK_URL, timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                if resp.status != 200:
                    log.warning("bce bulk: HTTP %d", resp.status)
                    return
                raw = await resp.read()

            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                # BCE ZIP contains: enterprise.csv, establishment.csv, activity.csv, address.csv
                # We join activity (NACE code) with establishment (address + name)
                activities: dict[str, str] = {}  # enterprise_number → nace_code
                for name in z.namelist():
                    if "activity" in name.lower() and name.endswith(".csv"):
                        with z.open(name) as f:
                            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
                            for row in reader:
                                nace = (row.get("NaceCode") or row.get("nace_code") or "")[:4]
                                if nace in _NACE_CODES:
                                    ent_no = row.get("EntityNumber") or row.get("enterprise_number", "")
                                    activities[ent_no] = nace

                # Now parse establishments for matching enterprises
                for name in z.namelist():
                    if "establishment" in name.lower() and name.endswith(".csv"):
                        with z.open(name) as f:
                            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
                            for row in reader:
                                ent_no = row.get("EnterpriseNumber") or row.get("enterprise_number", "")
                                if ent_no not in activities:
                                    continue
                                dealer = self._parse_establishment(row, activities[ent_no])
                                if dealer:
                                    yield dealer

        except Exception as exc:
            log.warning("bce bulk failed: %s", exc)
            return

    async def _crawl_search_api(self) -> AsyncGenerator[dict, None]:
        """Fallback: search BCE API by NACE activity code."""
        for nace in _NACE_CODES:
            page = 0
            while True:
                params = {
                    "naceCode": nace,
                    "start": str(page * 20),
                    "length": "20",
                    "actif": "true",
                }
                try:
                    async with self.session.get(
                        _SEARCH_API, params=params,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={"Accept": "application/json"},
                    ) as resp:
                        data = await resp.json(content_type=None)
                except Exception as exc:
                    log.warning("bce api nace=%s page=%d: %s", nace, page, exc)
                    break

                items = data.get("data") or []
                if not items:
                    break

                for item in items:
                    dealer = self._parse_api_item(item, nace)
                    if dealer:
                        yield dealer

                total = data.get("recordsTotal") or 0
                if (page + 1) * 20 >= total or len(items) < 20:
                    break
                page += 1
                await asyncio.sleep(0.5)

    @staticmethod
    def _parse_establishment(row: dict, nace_code: str) -> dict | None:
        try:
            name = row.get("Denomination") or row.get("denomination") or row.get("name")
            if not name:
                return None
            return {
                "source": "bce",
                "registry_id": row.get("EstablishmentNumber") or row.get("enterprise_number"),
                "name": name.strip(),
                "country": "BE",
                "lat": None,
                "lng": None,
                "address": row.get("StreetName", "") + " " + row.get("HouseNumber", ""),
                "city": row.get("Municipality"),
                "postcode": row.get("Zipcode"),
                "nace_code": nace_code,
                "website": None,
                "phone": None,
                "status": "active",
                "raw": row,
            }
        except Exception:
            return None

    @staticmethod
    def _parse_api_item(item: dict, nace_code: str) -> dict | None:
        try:
            name = item.get("denomination") or item.get("name", "")
            if not name:
                return None
            return {
                "source": "bce",
                "registry_id": item.get("vat") or item.get("enterpriseNumber"),
                "name": name.strip(),
                "country": "BE",
                "lat": None,
                "lng": None,
                "address": item.get("address"),
                "city": item.get("municipality"),
                "postcode": item.get("zipcode"),
                "nace_code": nace_code,
                "website": item.get("website"),
                "phone": None,
                "status": "active",
                "raw": item,
            }
        except Exception:
            return None
