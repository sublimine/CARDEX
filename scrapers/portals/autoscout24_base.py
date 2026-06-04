"""
AutoScout24 scraper base — the shared engine behind all 6 country variants.

AutoScout24 runs the same Next.js storefront on six TLDs (de/es/fr/nl/be/ch),
all behind Akamai v3 (domain_map → Tier.T2, escalates to T3). A country variant
is therefore just three facts: which TLD host to hit, which listing-path prefix
its deep links use, and which ISO country the inventory belongs to. Everything
else — the search-grid partition, the page-cap subdivision, the retry/softblock
loop, the Next.js JSON extraction — is identical and lives here.

Gold nuggets [VERIFIED 2026-04-28 against live HTML, carried from the legacy
Go pipeline's working AS24 path]:

  Search URL  /lst?atype=C&desc=0&sort=standard&page={N}
                  &year_from={Y}&year_to={Y2}[&price_to={P}][&fuel={F}]
  Listings    embedded in the Next.js JSON payload as "url":"/<prefix>/{slug}-{uuid}"
              — NOT in <a href>. Extracted by regex over the raw HTML body.
  Prefixes    DE /angebote/  FR /annonces/  ES /anuncios/  NL /aanbod/
              BE /annonces/ + /aanbod/   CH /annonces/ + /angebote/
  Pagination  20 listings/page, 20 pages max → 400 results/segment hard cap.
              A capped segment is subdivided by fuel type for full coverage.
  Grid        11 year bands × 8 cumulative price ceilings partition the inventory.

The grid's `price_to` ceilings are *cumulative* (a €4k car appears under every
ceiling), so segments overlap heavily. Cap detection therefore cannot count URLs
— BasePortalScraper detects the cap structurally (pagination exhausted MAX_PAGES),
which stays correct under that overlap. Cross-segment dedup is handled by the
base `seen` set, so overlap costs fetches but never double-emits a listing.

Anti-detection: a single curl_cffi AsyncSession is injected by the coordinator
(impersonate at session level — never per-request, that breaks JA3 coherence).
This module only issues GETs through the duck-typed `session`, so it imports and
unit-tests without curl_cffi present.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── search grid (verified gold nuggets) ───────────────────────────────────────
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
_PRICE_CEILINGS: tuple[int | None, ...] = (
    5_000, 10_000, 15_000, 20_000, 30_000, 50_000, 100_000, None,
)
_FUELS: tuple[str, ...] = ("P", "D", "E", "H")  # petrol / diesel / electric / hybrid

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
_CF_MARKERS: tuple[str, ...] = (
    "cf-browser-verification",
    "enable javascript and cookies to continue",
    "just a moment",
    "checking your browser",
    "__cf_chl_",
    "jschl-answer",
    "attention required! | cloudflare",
)


def _is_softblocked(html: str) -> bool:
    """True when a 200 body is actually a challenge page (soft block)."""
    lo = html.lower()
    return any(marker in lo for marker in _CF_MARKERS)


class AutoScout24Scraper(BasePortalScraper):
    """
    Concrete AS24 orchestration. A country variant subclasses this and sets
    DOMAIN, COUNTRY, HOST and LISTING_PREFIXES — nothing else.
    """

    # ── per-country knobs (subclass MUST set HOST + LISTING_PREFIXES) ──────────
    HOST: str = ""                       # request hostname, e.g. "www.autoscout24.de"
    LISTING_PREFIXES: tuple[str, ...] = ()  # deep-link path prefixes, e.g. ("/angebote/",)

    # ── grid + retry (overridable, but verified defaults) ─────────────────────
    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_CEILINGS: tuple[int | None, ...] = _PRICE_CEILINGS
    FUELS: tuple[str, ...] = _FUELS

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0      # seconds, exponentiated per attempt
    REQUEST_TIMEOUT: int = 20

    # ── derived request shape ─────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/lst"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `"url":"/<prefix>...id"` inside the Next.js JSON body."""
        alternation = "|".join(re.escape(p) for p in self.LISTING_PREFIXES)
        return re.compile(rf'"url":"((?:{alternation})[^"]+)"', re.IGNORECASE)

    def _validate(self) -> None:
        super()._validate()
        if not self.HOST or not self.LISTING_PREFIXES:
            raise ValueError(f"{type(self).__name__} must set HOST and LISTING_PREFIXES")

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band × cumulative price ceiling. Fuel stays empty until subdivision."""
        return [
            {"year_from": yf, "year_to": yt, "price_to": price, "fuel": ""}
            for (yf, yt), price in product(self.YEAR_BANDS, self.PRICE_CEILINGS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """A capped segment is split by fuel. An already fuel-split one cannot subdivide further."""
        if params.get("fuel"):
            return []
        return [{**params, "fuel": fuel} for fuel in self.FUELS]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page; retry block statuses / soft blocks; return deep-link URLs."""
        url = self._build_url(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url[:80])
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:80])
                return []

            html = response.text
            if _is_softblocked(html):
                log.warning("softblock (%d/%d) %s", attempt, self.RETRY_ATTEMPTS, url[:80])
                await self._retry_backoff(attempt, factor=2.0)
                continue

            return self._extract(html)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:80])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        url = (
            f"{self._search_base}?atype=C&desc=0&sort=standard"
            f"&year_from={params['year_from']}&year_to={params['year_to']}&page={page_num}"
        )
        price_to = params.get("price_to")
        if price_to is not None:
            url += f"&price_to={price_to}"
        fuel = params.get("fuel")
        if fuel:
            url += f"&fuel={fuel}"
        return url

    def _extract(self, html: str) -> list[str]:
        """Pull listing deep links from the Next.js JSON, deduped within the page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            full = self._base_url + match.group(1)
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        """One GET; None on transport error so the retry loop can back off."""
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("transport error %s: %s", url[:80], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Exponential backoff, skipped on the final attempt (about to give up)."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
