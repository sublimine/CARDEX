"""
mobile.de scraper — the HTML search-results path behind Akamai Bot Manager.

mobile.de exposes two access methods, and they are deliberately split across two
registry entries so the engine can route each independently:

  * `mobile.de`        → Tier.T0, the Ad-Stream WSS mobile-API consumer (a wholly
                         different code path; see the T0 pipeline).
  * `suchen.mobile.de` → Tier.T2, THIS scraper: the public search-results page
                         (suchen.mobile.de/fahrzeuge/search.html) behind Akamai v3,
                         used as the browser-tier fallback when the API path is
                         unavailable. DOMAIN is `suchen.mobile.de` precisely so
                         domain_map routes it to T2/Akamai, never to the T0 entry.

Search-grid → query mapping [ASSUMED — search.html parameter names inferred from
the classic mobile.de SRP query string, not re-verified against live HTML this
cycle; the path and the detail-link shape are the stable, long-lived parts]:

  Search URL  /fahrzeuge/search.html?vc=Car&isSearchRequest=true&ref=srp
                  &fr={year_from}:{year_to}      first-registration range
                  &p={price_from}:{price_to}     price range (open-ended → "p=N:")
                  &pageNumber={n}
  Listings    /fahrzeuge/details.html?id={digits}, extracted by regex over the
              HTML body (deep links, deduped within the page).

Akamai soft-block: a sensor-rejected request is usually a 403 (handled by the
base BLOCK_STATUSES retry) or a 200 "Access Denied" / Akamai reference page.
_is_soft_block therefore ORs the base WAF-classifier verdict with mobile.de's
own access-denied body markers so a 200 challenge page is retried, never parsed.
"""
from __future__ import annotations

import re
from functools import cached_property
from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

# Akamai "you were blocked" interstitials served with a 200 status. Lowercased.
_AKAMAI_DENY_MARKERS: tuple[str, ...] = (
    "access denied",
    "you don't have permission to access",
    "reference #",
    "errors.edgesuite.net",
)


class MobileDeScraper(HttpPortalScraper):
    """mobile.de search-results scraper (browser tier, Akamai v3)."""

    DOMAIN = "suchen.mobile.de"
    COUNTRY = "DE"

    HOST = "suchen.mobile.de"
    # mobile.de paginates ~20 results/page and caps deep pagination well before
    # the inventory is exhausted, so a capped segment is subdivided by price. [ASSUMED]
    PAGE_SIZE = 20
    MAX_PAGES = 50

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/fahrzeuge/details.html?id={digits}` deep links in the HTML body."""
        return re.compile(r"/fahrzeuge/details\.html\?id=(\d+)")

    # ── primitives ──────────────────────────────────────────────────────────────
    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        price_to = params["price_to"]
        price = f"{params['price_from']}:{'' if price_to is None else price_to}"
        url = (
            f"{self._base_url}/fahrzeuge/search.html"
            f"?vc=Car&isSearchRequest=true&ref=srp&sb=rel&od=up&dam=false"
            f"&fr={params['year_from']}:{params['year_to']}"
            f"&p={price}"
            f"&pageNumber={page_num}"
        )
        return PortalRequest(url=url)

    def _extract(self, response: Any) -> list[str]:
        """Pull `details.html?id=…` deep links from the HTML, deduped within the page."""
        html = self._response_text(response)
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            full = f"{self._base_url}/fahrzeuge/details.html?id={match.group(1)}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out

    def _is_soft_block(self, response: Any) -> bool:
        """Base WAF verdict OR an Akamai 200 'Access Denied' / reference page."""
        if super()._is_soft_block(response):
            return True
        body_lc = self._response_text(response).lower()
        return any(marker in body_lc for marker in _AKAMAI_DENY_MARKERS)
