"""
INSEE SIRENE — France's official business registry (open data).

SIRENE is maintained by INSEE (Institut national de la statistique et des
études économiques). ALL businesses legally operating in France are registered.
Car dealers = NAF/APE code 4511Z (Commerce de voitures et de véhicules automobiles légers).

Data access:
  - Full dataset: https://www.data.gouv.fr/fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/
  - API: https://api.entreprise.api.gouv.fr/ (requires SIRET auth)
  - Public search API: https://recherche-entreprises.api.gouv.fr/search (NO AUTH NEEDED)
    → GET /search?activite_principale=4511Z&per_page=25&page=N

This returns every establishment (not just head office) with address,
SIRET, name, coordinates (lat/lon), status (active/inactive).
We filter: etat_administratif = "A" (active).
~40,000 active car dealer establishments in France.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

# French government's free entreprise search API — no auth required
_SEARCH_API = "https://recherche-entreprises.api.gouv.fr/search"
_NAF_CODES = [
    "4511Z",  # Commerce de voitures et de véhicules automobiles légers
    "4519Z",  # Commerce d'autres véhicules automobiles
    "4520A",  # Entretien et réparation de véhicules automobiles légers (often sell too)
]
_PAGE_SIZE = 25


class FRSIRENECrawler:
    """
    Downloads all active car dealer establishments from INSEE SIRENE via
    the free French government open-data API.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:sirene_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:sirene_done", "1", ex=30 * 86400)  # monthly refresh

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("sirene: already done (within 30 days)")
            return

        total_yielded = 0
        for naf in _NAF_CODES:
            page = 1
            while True:
                params = {
                    "activite_principale": naf,
                    "etat_administratif": "A",   # active only
                    "per_page": str(_PAGE_SIZE),
                    "page": str(page),
                }
                try:
                    async with self.session.get(
                        _SEARCH_API, params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"Accept": "application/json"},
                    ) as resp:
                        data = await resp.json()
                except Exception as exc:
                    log.warning("sirene naf=%s page=%d: %s", naf, page, exc)
                    await asyncio.sleep(5)
                    break

                results = data.get("results") or []
                if not results:
                    break

                for r in results:
                    dealer = self._parse(r)
                    if dealer:
                        total_yielded += 1
                        yield dealer

                total_pages = data.get("total_pages") or 1
                if page >= total_pages or len(results) < _PAGE_SIZE:
                    break

                page += 1
                await asyncio.sleep(0.3)  # respect API rate limit

        log.info("sirene: yielded %d FR dealers", total_yielded)
        await self._mark_done()

    @staticmethod
    def _parse(r: dict) -> dict | None:
        try:
            # Each result has 'matching_etablissements' — we want the siege social
            # or all establishments depending on how granular we need
            siege = r.get("siege") or {}
            name = r.get("nom_complet") or r.get("nom_raison_sociale") or siege.get("libelle_voie")
            if not name:
                return None

            lat = siege.get("latitude")
            lng = siege.get("longitude")

            return {
                "source": "sirene",
                "registry_id": siege.get("siret") or r.get("siren"),
                "name": name,
                "country": "FR",
                "lat": float(lat) if lat else None,
                "lng": float(lng) if lng else None,
                "address": " ".join(filter(None, [
                    siege.get("numero_voie"),
                    siege.get("type_voie"),
                    siege.get("libelle_voie"),
                ])),
                "city": siege.get("libelle_commune"),
                "postcode": siege.get("code_postal"),
                "naf_code": r.get("activite_principale"),
                "website": None,  # not in SIRENE, enriched later
                "phone": None,
                "status": "active",
                "raw": r,
            }
        except Exception:
            return None
