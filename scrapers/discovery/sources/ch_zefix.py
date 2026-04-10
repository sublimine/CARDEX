"""
Zefix — Switzerland's central commercial register.

Zefix is maintained by the Swiss Federal Office of Justice (EJPD/BJ) and
indexes every company registered in any of the 26 cantonal commercial
registers. The public REST API lives at:

    https://www.zefix.admin.ch/ZefixPublicREST/

It exposes a JSON company-search endpoint that accepts a name fragment,
canton filter, and deleted-firms toggle. No authentication, no rate limit
beyond normal politeness.

Zefix does not index companies by NOGA activity code in the public search,
so we do a per-canton × per-keyword sweep and filter by a car-trade lexicon
in the response. This catches every company whose legal name contains
"autohaus", "garage", "automobil", "voiture", etc. — the standard self-
identification patterns for Swiss car dealers. Companies with generic
names (e.g. "Müller AG" that happens to sell cars) are missed by name-
based search; those are picked up later by OSM / portal_aggregator.

Output dict shape matches discovery_candidates.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

_ZEFIX_BASE = os.environ.get(
    "ZEFIX_BASE_URL",
    "https://www.zefix.admin.ch/ZefixPublicREST/api/v1",
)
_SEARCH_URL = f"{_ZEFIX_BASE}/company/search"

# 26 Swiss cantons — ISO 3166-2:CH codes.
_CANTONS: tuple[str, ...] = (
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR",
    "JU", "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG",
    "TI", "UR", "VD", "VS", "ZG", "ZH",
)

# Name fragments used to bias the search towards motor trade.
_SEARCH_TERMS: tuple[str, ...] = (
    "auto", "autohaus", "automobil", "garage", "voiture",
    "occasion", "fahrzeug", "car", "motor",
)

# Keywords used to filter returned companies down to motor trade.
_DEALER_KEYWORDS: tuple[str, ...] = (
    "auto", "garage", "voiture", "fahrzeug", "car",
    "occasions", "concessionnaire", "automobil", "motor",
)

_PAGE_SIZE = 100
_PAGE_DELAY = 0.25


class ZefixSource:
    """
    Yields CH car dealer companies from Zefix via per-canton × per-term sweep.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def discover(self, country: str = "CH") -> AsyncIterator[dict]:
        if country != "CH":
            return

        seen_uids: set[str] = set()
        total = 0

        for canton in _CANTONS:
            for term in _SEARCH_TERMS:
                async for cand in self._search(canton, term, seen_uids):
                    total += 1
                    yield cand
                await asyncio.sleep(_PAGE_DELAY)

        log.info("zefix: CH — %d candidate companies", total)

    async def _search(
        self, canton: str, term: str, seen: set[str],
    ) -> AsyncIterator[dict]:
        offset = 0
        while True:
            payload = {
                "name":          term,
                "canton":        canton,
                "deletedFirms":  False,
                "maxEntries":    _PAGE_SIZE,
                "offset":        offset,
            }
            try:
                resp = await self._client.post(
                    _SEARCH_URL,
                    json=payload,
                    headers={"Accept": "application/json"},
                    timeout=20.0,
                )
            except Exception as exc:
                log.warning("zefix canton=%s term=%s: %s", canton, term, exc)
                return

            if resp.status_code != 200:
                log.debug("zefix canton=%s term=%s HTTP %d",
                          canton, term, resp.status_code)
                return

            try:
                data = resp.json()
            except Exception:
                return

            items = data.get("list") or data.get("companies") or []
            if not items:
                return

            for item in items:
                uid = str(item.get("uid") or item.get("cheId") or item.get("id") or "")
                if not uid or uid in seen:
                    continue
                seen.add(uid)

                name = (item.get("name") or item.get("firma") or "").strip()
                if not name:
                    continue
                if not _is_motor_trade(name):
                    continue

                cand = _to_candidate(item, name, uid, canton)
                if cand:
                    yield cand

            if len(items) < _PAGE_SIZE:
                return
            offset += _PAGE_SIZE


def _is_motor_trade(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in _DEALER_KEYWORDS)


def _to_candidate(item: dict, name: str, uid: str, canton: str) -> dict | None:
    address = item.get("address") or item.get("adresse") or {}
    if isinstance(address, str):
        addr_str = address
        city = None
        postcode = None
    else:
        addr_str = " ".join(filter(None, (
            address.get("street") or address.get("strasse"),
            str(address.get("houseNumber") or address.get("hausnummer") or "").strip(),
        ))).strip() or None
        city = address.get("city") or address.get("ort")
        postcode = address.get("swissZipCode") or address.get("plz")

    return {
        "domain":       None,
        "country":      "CH",
        "source_layer": 3,
        "source":       "zefix",
        "url":          None,
        "name":         name,
        "address":      addr_str,
        "city":         city,
        "postcode":     str(postcode) if postcode else None,
        "phone":        None,
        "email":        None,
        "lat":          None,
        "lng":          None,
        "registry_id":  uid,
        "external_refs": {
            "canton":      item.get("canton") or item.get("kanton") or canton,
            "legal_form":  item.get("legalForm") or item.get("rechtsform"),
            "status":      "inactive" if item.get("deleted") else "active",
        },
    }
