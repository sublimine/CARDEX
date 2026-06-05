"""
kleinanzeigen.de scraper — the HTML search-results path behind Cloudflare (Tier.T1).

kleinanzeigen.de (the former eBay Kleinanzeigen) renders its car classifieds
server-side, so the cheapest correct path is a plain GET against the cars SRP and
a regex over the returned HTML for detail deep links. domain_map routes it to T1
(curl_cffi chrome impersonation, no browser) behind Cloudflare Pro — a challenged
request is the standard CF interstitial the base WAF-classifier already flags, so
no _is_soft_block override is needed here.

Search-grid → URL mapping [ASSUMED — the SRP path segments are inferred from the
long-stable kleinanzeigen URL grammar (category code `c216` = Autos, `preis:` and
`seite:` path filters, the `c216+autos.ez_i:` attribute-filter suffix for the
first-registration range); not re-verified against live HTML this cycle. The
`/s-anzeige/{slug}/{id}` detail-link shape is the stable, long-lived part]:

  Search URL  /s-autos/preis:{price_from}:{price_to}/seite:{n}
                  /c216+autos.ez_i:{year_from},{year_to}
              price open-ended → trailing empty ("preis:100000:")
  Listings    /s-anzeige/{slug}/{digits}-{digits}-{digits}, extracted by regex
              over the HTML body (deep links, deduped within the page).
"""
from __future__ import annotations

import re
from functools import cached_property
from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

# Autos category code in the kleinanzeigen URL grammar. [ASSUMED — long-stable value]
_CARS_CATEGORY = "c216"


class KleinanzeigenScraper(HttpPortalScraper):
    """kleinanzeigen.de cars scraper (curl_cffi tier, Cloudflare Pro)."""

    DOMAIN = "kleinanzeigen.de"
    COUNTRY = "DE"

    HOST = "www.kleinanzeigen.de"
    # kleinanzeigen paginates ~25 results/page and caps deep pagination, so a capped
    # price window is subdivided rather than paged past the ceiling. [ASSUMED]
    PAGE_SIZE = 25
    MAX_PAGES = 50

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/s-anzeige/{slug}/{id}` deep links in the HTML body."""
        return re.compile(r"/s-anzeige/[a-zA-Z0-9-]+/\d+-\d+-\d+")

    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        price_to = params["price_to"]
        price = f"{params['price_from']}:{'' if price_to is None else price_to}"
        url = (
            f"{self._base_url}/s-autos"
            f"/preis:{price}"
            f"/seite:{page_num}"
            f"/{_CARS_CATEGORY}+autos.ez_i:{params['year_from']},{params['year_to']}"
        )
        return PortalRequest(url=url)

    def _extract(self, response: Any) -> list[str]:
        """Pull `/s-anzeige/…` deep links from the HTML, deduped within the page."""
        html = self._response_text(response)
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            full = f"{self._base_url}{match.group(0)}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out
