"""
Zefix (Zentraler Firmenindex) — Switzerland's official commercial register.

Zefix is the central index of all companies registered in Switzerland's
cantonal commercial registers (Handelsregister). It's maintained by the
Swiss Federal Justice and Police Department (EJPD).

Data access:
  REST API: https://www.zefix.admin.ch/ZefixREST/api/v1/
  → GET /firm/search.json — search by legal form + activity
  → No authentication required for public search
  → Returns CHE number, company name, canton, address, status

NOGA code for car dealers: 4511 (Handel mit Personenkraftwagen)
CH uses NOGA (Swiss classification, maps to NACE).

~12,000 active car dealer companies in Switzerland (cantons: ZH, BE, GE, VD, AG, etc.)
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

_ZEFIX_SEARCH_API = "https://www.zefix.admin.ch/ZefixREST/api/v1/firm/search.json"
_ZEFIX_COMPANY_API = "https://www.zefix.admin.ch/ZefixREST/api/v1/company/{uid}.json"

# Swiss cantons (all 26) — we search per canton for complete coverage
_CANTONS = [
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR",
    "JU", "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG",
    "TI", "UR", "VD", "VS", "ZG", "ZH",
]

_SEARCH_TERMS = [
    "autohaus", "automobil", "auto AG", "voiture", "occasion",
    "garage auto", "autohandel", "fahrzeug", "car",
]

_PAGE_SIZE = 50


class CHZefixCrawler:
    """
    Discovers all Swiss car dealers from the Zefix central commercial register.
    Searches per canton × search term to ensure complete coverage.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:zefix_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:zefix_done", "1", ex=30 * 86400)

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("zefix: already done (within 30 days)")
            return

        seen_uids: set[str] = set()
        total = 0

        for canton in _CANTONS:
            for term in _SEARCH_TERMS:
                async for dealer in self._search(canton, term, seen_uids):
                    total += 1
                    yield dealer
                await asyncio.sleep(0.2)

        log.info("zefix: yielded %d CH dealers", total)
        if total > 0:
            await self._mark_done()

    async def _search(self, canton: str, term: str, seen: set) -> AsyncGenerator[dict, None]:
        start = 0
        while True:
            payload = {
                "name": term,
                "canton": canton,
                "deletedFirms": False,
                "maxEntries": _PAGE_SIZE,
                "offset": start,
            }
            try:
                async with self.session.post(
                    _ZEFIX_SEARCH_API,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                    headers={"Accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()
            except Exception as exc:
                log.warning("zefix canton=%s term=%s: %s", canton, term, exc)
                return

            items = data.get("list") or []
            if not items:
                return

            for item in items:
                uid = item.get("uid") or item.get("cheId") or item.get("id")
                if not uid:
                    continue
                uid_str = str(uid)
                if uid_str in seen:
                    continue
                seen.add(uid_str)

                # Filter: only include likely car dealers
                name_lower = (item.get("name") or "").lower()
                if not any(kw in name_lower for kw in [
                    "auto", "garage", "voiture", "fahrzeug", "car",
                    "occasions", "concessionnaire", "automobil",
                ]):
                    continue

                dealer = self._parse(item)
                if dealer:
                    yield dealer

            if len(items) < _PAGE_SIZE:
                return
            start += _PAGE_SIZE

    @staticmethod
    def _parse(item: dict) -> dict | None:
        try:
            name = item.get("name") or item.get("firma")
            if not name:
                return None

            address = item.get("address") or item.get("adresse") or {}
            if isinstance(address, str):
                addr_str = address
                city = None
                postcode = None
            else:
                addr_str = " ".join(filter(None, [
                    address.get("street") or address.get("strasse"),
                    str(address.get("houseNumber") or address.get("hausnummer") or ""),
                ]))
                city = address.get("city") or address.get("ort")
                postcode = address.get("swissZipCode") or address.get("plz")

            return {
                "source": "zefix",
                "registry_id": item.get("uid") or item.get("cheId"),
                "name": name.strip(),
                "country": "CH",
                "canton": item.get("canton") or item.get("kanton"),
                "lat": None,
                "lng": None,
                "address": addr_str,
                "city": city,
                "postcode": str(postcode) if postcode else None,
                "website": None,
                "phone": None,
                "status": "active" if not item.get("deleted") else "inactive",
                "raw": item,
            }
        except Exception:
            return None
