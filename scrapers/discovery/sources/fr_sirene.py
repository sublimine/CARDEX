"""
INSEE SIRENE — French government business registry, open API.

API: https://recherche-entreprises.api.gouv.fr/search
    — free, no auth, no rate limit beyond politeness
    — filters by NAF activity code, postal department, status
    — hard cap: page × per_page ≤ 10_000 per query

Car dealer NAF codes:
    4511Z — Commerce de voitures et de véhicules automobiles légers
    4519Z — Commerce d'autres véhicules automobiles
    4520A — Entretien et réparation de véhicules automobiles légers

A single unfiltered query hits the 10k cap immediately. We partition by
`departement` (≈100 French departments) — no department has close to 10k
car dealers, so per-department pagination drains the full inventory.

Each API result is a unité légale; the establishments matching the NAF
filter live in `matching_etablissements`. We yield one candidate per
matching establishment (so a chain with 30 branches produces 30 rows,
not 1).

Output dict shape is compatible with discovery_candidates.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

_API_URL = "https://recherche-entreprises.api.gouv.fr/search"
_PAGE_SIZE = 25
_PAGE_DELAY = 0.25  # polite pacing between API calls

_NAF_CODES = ("4511Z", "4519Z", "4520A")

# Metropolitan France departments (96) + overseas (5).
_DEPARTEMENTS: tuple[str, ...] = (
    "01", "02", "03", "04", "05", "06", "07", "08", "09",
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "2A", "2B",
    "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
    "60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
    "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "90", "91", "92", "93", "94", "95",
    "971", "972", "973", "974", "976",
)


class SireneSource:
    """
    Yields FR car dealer establishments from INSEE SIRENE, partitioned by
    department × NAF code to avoid the API's 10_000-result hard cap.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def discover(self, country: str = "FR") -> AsyncIterator[dict]:
        if country != "FR":
            return

        total = 0
        for dep in _DEPARTEMENTS:
            for naf in _NAF_CODES:
                async for cand in self._query(dep, naf):
                    total += 1
                    yield cand

        log.info("sirene: FR — %d candidate establishments", total)

    async def _query(self, dep: str, naf: str) -> AsyncIterator[dict]:
        page = 1
        while True:
            params = {
                "activite_principale": naf,
                "departement": dep,
                "etat_administratif": "A",
                "per_page": str(_PAGE_SIZE),
                "page": str(page),
            }
            try:
                resp = await self._client.get(
                    _API_URL,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=30.0,
                )
            except Exception as exc:
                log.warning("sirene dep=%s naf=%s page=%d: %s", dep, naf, page, exc)
                return

            if resp.status_code != 200:
                log.debug("sirene dep=%s naf=%s page=%d HTTP %d",
                          dep, naf, page, resp.status_code)
                return

            try:
                data = resp.json()
            except Exception:
                return

            results = data.get("results") or []
            if not results:
                return

            for unite in results:
                for cand in _unite_to_candidates(unite, naf):
                    yield cand

            total_pages = data.get("total_pages") or 1
            if page >= total_pages or len(results) < _PAGE_SIZE:
                return

            page += 1
            await asyncio.sleep(_PAGE_DELAY)


def _unite_to_candidates(unite: dict, naf: str) -> list[dict]:
    """
    Expand one unité légale into one candidate per matching establishment.
    Falls back to siège social if matching_etablissements is absent.
    """
    name = (
        unite.get("nom_complet")
        or unite.get("nom_raison_sociale")
        or ""
    ).strip()
    if not name:
        return []

    etabs = unite.get("matching_etablissements") or []
    if not etabs:
        siege = unite.get("siege") or {}
        if siege:
            etabs = [siege]

    out: list[dict] = []
    for e in etabs:
        siret = e.get("siret") or unite.get("siren")
        if not siret:
            continue

        lat = _maybe_float(e.get("latitude"))
        lng = _maybe_float(e.get("longitude"))

        address = " ".join(filter(None, (
            e.get("numero_voie"),
            e.get("type_voie"),
            e.get("libelle_voie"),
        ))).strip() or None

        out.append({
            "domain":       None,            # SIRENE does not expose websites
            "country":      "FR",
            "source_layer": 3,
            "source":       "sirene",
            "url":          None,
            "name":         name,
            "address":      address,
            "city":         e.get("libelle_commune"),
            "postcode":     e.get("code_postal"),
            "phone":        None,
            "email":        None,
            "lat":          lat,
            "lng":          lng,
            "registry_id":  siret,
            "external_refs": {
                "naf_code": naf,
                "siren":    unite.get("siren"),
                "departement": e.get("departement"),
            },
        })
    return out


def _maybe_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
