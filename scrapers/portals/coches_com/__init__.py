"""
coches.com — Spain, Adevinta group automotive portal (~50k listings).

T2 (Cloudflare Pro): returns 403 blocked-by-allowlist on datacenter IPs.
Uses Adevinta Spain's custom @s-ui/ssr framework (not Next.js), so no
/_next/data/ routes.  Does NOT share the Marktplaats LRP API — Adevinta
Spain runs a completely separate platform stack.

NOTE: Lower priority portal.  coches.net (already LIVE, T1) covers ~300k
listings from the same Adevinta Spain pool.  coches.com has incremental
inventory of ~50k listings not on coches.net (primarily private sellers).

Approach: SSR HTML parsing via Camoufox.  The search results page renders
listing cards server-side with @s-ui/ssr.  Extract listing URLs from the
HTML after passing CF JS challenge.

Gold nuggets [research 2026-06-04]:

  Search URL    /segunda-mano/?pg={N}                              [INFERRED]
                /segunda-mano/?precio_desde={P}&precio_hasta={P}
  Framework     @s-ui/ssr (Adevinta custom React SSR)              [CONFIRMED]
  WAF           Cloudflare Pro, 403 blocked-by-allowlist           [CONFIRMED]
  Block signal  X-Proxy-Error: blocked-by-allowlist header         [CONFIRMED]
  Sibling       coches.net (same group, separate API, already LIVE)[CONFIRMED]
  Inventory     ~50k listings                                      [ESTIMATED]

Partition: price bands (EUR).  Spanish market distribution.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.coches.com/segunda-mano/"

# ── price bands (EUR) ────────────────────────────────────────────────────────
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0,     3_000),
    (3_000, 5_000),
    (5_000, 8_000),
    (8_000, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 30_000),
    (30_000, 50_000),
    (50_000, None),
)

# Listing URL patterns in @s-ui/ssr HTML
_LISTING_LINK_RE = re.compile(
    r'href="(/[^"]*?/(?:oferta|anuncio)/[^"]+)"', re.IGNORECASE
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?coches\.com/[^"]*?/(?:oferta|anuncio)/[^"]+)"',
    re.IGNORECASE,
)


class CochesComESScraper(BasePortalScraper):
    """SSR HTML scraper for coches.com (T2, Cloudflare Pro)."""

    DOMAIN = "coches.com"
    COUNTRY = "ES"

    PAGE_SIZE = 30
    MAX_PAGES = 50

    SLEEP_BASE = 2.0
    SLEEP_JITTER = 0.8

    def partition_params(self) -> list[dict[str, Any]]:
        """Price band segments."""
        return [
            {"price_from": pf, "price_to": pt}
            for pf, pt in _PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page via Camoufox, extract listing URLs."""
        price_from = params["price_from"]
        price_to = params.get("price_to")

        url = f"{_BASE_URL}?pg={page_num}&precio_desde={price_from}"
        if price_to is not None:
            url += f"&precio_hasta={price_to}"

        try:
            resp = await session.get(url, timeout=30)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("coches.com transport error %s: %s", url[:90], exc)
            return []
        if resp.status_code != 200:
            log.warning(
                "coches.com status=%d price=%d-%s page=%d",
                resp.status_code, price_from, price_to, page_num,
            )
            return []

        if "challenge-platform" in resp.text or "Just a moment" in resp.text:
            log.warning("coches.com CF challenge on page %d", page_num)
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split price band in half."""
        pf = params["price_from"]
        pt = params.get("price_to")
        if pt is None or (pt - pf) <= 1_000:
            return []
        mid = pf + (pt - pf) // 2
        return [
            {"price_from": pf, "price_to": mid},
            {"price_from": mid, "price_to": pt},
        ]


def _extract_listing_urls(html: str) -> list[str]:
    """Extract listing URLs from @s-ui/ssr rendered HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.coches.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
