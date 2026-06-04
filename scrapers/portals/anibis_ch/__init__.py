"""
anibis.ch — Suiza, portal de clasificados francófono (~78k coches).

Gemelo idéntico de tutti.ch sobre el mismo backend Scout24. Comparte inventario,
tokens msgpack, data route Next.js y estructura de respuesta. Solo difieren:
  HOST          www.anibis.ch
  LANG          fr (vs. de en tutti.ch)
  CATEGORY_SLUG voitures (vs. autos)
  SLUG_KEY      frSlug (vs. deSlug)

Gold nuggets [VERIFIED 2026-06-04 — docs/research/anibis-ch.md]:

  Data route  GET /_next/data/{buildId}/fr/q/voitures/{token}.json?page={N}
  Token       idéntico a tutti.ch — 'A' + base64url(msgpack(...))
  Listings    .pageProps.dehydratedState.queries[0].state.data.listings.edges[].node
  Detail URL  https://www.anibis.ch/fr/vi/{listingID}/{frSlug}
  Pagination  ?page=N; cap en 101 (30 items/pag = 3,030 max por token)
  buildId     cambia con deploys; extraer de __NEXT_DATA__ en HTML SSR (/fr)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from scrapers.portals.tutti_ch import TuttiCHScraper, _encode_token, _BUILD_ID_RE

log = logging.getLogger(__name__)


class AnibisCHScraper(TuttiCHScraper):
    """anibis.ch coches — clon francés de tutti.ch (T1, mismo backend Scout24)."""

    DOMAIN = "anibis.ch"
    COUNTRY = "CH"

    HOST = "www.anibis.ch"
    # PAGE_SIZE, MAX_PAGES, RETRY_*, BRANDS, PRICE_BANDS heredados de TuttiCHScraper

    # ── overrides de locale ───────────────────────────────────────────────

    LANG: str = "fr"
    CATEGORY_SLUG: str = "voitures"
    SLUG_KEY: str = "frSlug"

    # ── helpers redefinidos para locale francés ────────────────────────────

    def _build_data_url(self, token: str, page_num: int) -> str:
        base = (
            f"{self._base_url}/_next/data/{self._build_id}"
            f"/{self.LANG}/q/{self.CATEGORY_SLUG}/{token}.json"
        )
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, body: str) -> list[str]:
        """Extrae URLs de detalle del JSON — usa frSlug en vez de deSlug."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("cuerpo no-JSON desde anibis.ch data route")
            return []
        try:
            edges = (
                payload["pageProps"]["dehydratedState"]["queries"][0]
                ["state"]["data"]["listings"]["edges"]
            )
        except (KeyError, IndexError, TypeError):
            return []
        if not isinstance(edges, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for edge in edges:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict):
                continue
            listing_id = node.get("listingID")
            seo = node.get("seoInformation")
            slug = seo.get(self.SLUG_KEY) if isinstance(seo, dict) else None
            if not listing_id:
                continue
            if slug:
                url = f"{self._base_url}/{self.LANG}/vi/{listing_id}/{slug}"
            else:
                url = f"{self._base_url}/{self.LANG}/vi/{listing_id}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _resolve_build_id(self, session: Any) -> str | None:
        """Extrae buildId desde HTML SSR de la landing francesa."""
        response = await self._get(session, f"{self._base_url}/{self.LANG}")
        if response is None or response.status_code != 200:
            log.error("no se pudo resolver buildId de anibis.ch")
            return None
        match = _BUILD_ID_RE.search(response.text)
        if not match:
            log.error("buildId no encontrado en HTML de anibis.ch")
            return None
        build_id = match.group(1)
        log.info("anibis.ch buildId resuelto: %s", build_id)
        return build_id
