"""
autoboerse.de — Germany, Santander dealer marketplace (~250K vehicles).

Pure SSR HTML, no WAF, brand-based path filtering with query-param pagination
and price ranges. 18 listings per page. Detail URLs contain a 12-character
base64url ID as the final path segment. First-party dealer inventory from
Santander-partnered dealerships — NOT aggregated from autoscout24/mobile.de.

Gold nuggets [VERIFIED 2026-06-04 — docs/research/phase6-portal-probe-results.md]:

  Search base  GET https://autoboerse.de/fahrzeugsuche
  Brand filter /fahrzeugsuche/{brand-slug}/  (path segment, lowercase+hyphens)
  Pagination   ?page=N  (1-indexed, 18 listings/page)
  Price query  ?preis_ab=N&preis_bis=N  (EUR, integer)
  Detail URL   /fahrzeugsuche/{brand-model-fuel-region}/{12-char-base64url-id}
  Listing re   /fahrzeugsuche/[a-z0-9][a-z0-9_-]+/[A-Za-z0-9_-]{12}
  WAF          NONE (T1) — Openbank Deutschland AG (Santander group)
  Inventory    250,164 from "geprüfte Händlerpartner" (verified dealer partners)
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})

# Complete brand slug list extracted from autoboerse.de/fahrzeugsuche [2026-06-04].
# These are path segments used by the site itself — no guesswork.
_BRANDS: tuple[str, ...] = (
    "abarth", "aixam", "alfa-romeo", "alpina", "alpine", "aston-martin",
    "audi", "austin", "baic", "bentley", "bmw", "borgward", "buick",
    "byd", "cadillac", "casalini", "cenntro", "chevrolet", "chrysler",
    "citroen", "cobra", "corvette", "cupra", "dacia", "daf", "daihatsu",
    "detomaso", "dfsk", "dodge", "dr-automobiles", "ds-automobiles",
    "ego", "elaris", "etrusco", "ferrari", "fiat", "fisker", "ford",
    "forthing", "genesis", "gmc", "gwm", "honda", "hummer", "hyundai",
    "ineos", "infiniti", "isuzu", "iveco", "jac", "jaguar", "jeep",
    "kgm--ssangyong", "kia", "ktm", "lada", "lamborghini", "lancia",
    "land-rover", "levc", "lexus", "ligier", "lincoln", "lotus", "lucid",
    "lynk-_-co", "man", "maserati", "maxus", "maybach", "mazda", "mclaren",
    "mercedes-benz", "mg", "microcar", "microlino", "mini", "mitsubishi",
    "morgan", "nio", "nissan", "nsu", "oldsmobile", "opel", "ora",
    "peugeot", "piaggio", "plymouth", "polestar", "porsche", "ram",
    "renault", "rolls-royce", "rover", "saab", "seat", "seres", "silence",
    "skoda", "smart", "ssangyong", "subaru", "suzuki", "swm", "tesla",
    "toyota", "triumph", "volkswagen", "volvo", "wartburg", "wey",
    "wiesmann", "xev", "xpeng",
)

# Non-overlapping EUR price bands for subdivision of high-volume brand segments.
# Top band is open-ended (preis_bis=None → omit param).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)


class AutoboerseDEScraper(BasePortalScraper):
    """autoboerse.de vehicles via SSR HTML brand pages (T1)."""

    DOMAIN = "autoboerse.de"
    COUNTRY = "DE"

    HOST = "autoboerse.de"

    # 18 listings per page (verified); hard cap unknown but conservative MAX_PAGES.
    PAGE_SIZE = 18
    MAX_PAGES = 50  # 18 × 50 = 900 per segment — triggers subdivide for big brands

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── request shape ─────────────────────────────────────────────────────────

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        r"""Match /fahrzeugsuche/{slug}/{12-char-base64url-id} in raw HTML.

        Slug = lowercase brand-model-fuel-region (e.g. volkswagen-tiguan-sachsen).
        ID   = exactly 12 chars from [A-Za-z0-9_-] (base64url, no padding).
        """
        return re.compile(r"/fahrzeugsuche/[a-z0-9][a-z0-9_-]+/[A-Za-z0-9_-]{12}(?=[\"'\s?#&]|$)")

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per brand slug — 115 brands covering the full inventory."""
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a capped brand segment into price-band sub-segments."""
        if params.get("_fine"):
            return []
        return [
            {
                "brand": params["brand"],
                "preis_ab": pf,
                "preis_bis": pt,
                "_fine": True,
            }
            for pf, pt in self.PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one HTML search page; retry on transient blocks."""
        url = self._build_url(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug(
                    "HTTP %d (%d/%d) %s",
                    status, attempt, self.RETRY_ATTEMPTS, url[:90],
                )
                await self._retry_backoff(attempt)
                continue

            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        brand = params["brand"]
        base = f"https://{self.HOST}/fahrzeugsuche/{brand}/"

        qp: list[str] = []
        if "preis_ab" in params:
            qp.append(f"preis_ab={params['preis_ab']}")
        if params.get("preis_bis") is not None:
            qp.append(f"preis_bis={params['preis_bis']}")
        qp.append(f"page={page_num}")

        return f"{base}?{'&'.join(qp)}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from listing hrefs, deduped within page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            path = match.group(0)
            url = f"https://{self.HOST}{path}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
