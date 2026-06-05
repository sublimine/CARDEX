"""
marktplaats.nl scraper — the lrp JSON search API behind Cloudflare (Tier.T1).

marktplaats.nl exposes a JSON "listing results page" (lrp) search endpoint that its
own web front-end consumes, so the cheapest correct path is a GET against that API
and reading deep links out of the JSON. domain_map routes it to T1 (curl_cffi,
no browser) behind Cloudflare Pro; a challenged request is the standard CF
interstitial the base WAF-classifier already flags, so no _is_soft_block override
is needed.

Although it returns JSON, the endpoint is a GET (query-string filters), so the
request is the base GET path and the JSON is parsed in _extract.

Search-grid → query mapping [ASSUMED — parameter names inferred from the marktplaats
lrp search contract: cars L1 category `91`, cents-denominated `PriceCents` and
`constructionYear` attribute ranges, offset/limit pagination; NOT re-verified live
this cycle. The `listings[].vipUrl` detail-link shape is the more stable part]:

  GET /lrp/api/search?l1CategoryId=91
          &offset={(n-1)*limit}&limit={limit}
          &attributesByKey[]=PriceCents:{price_from*100}:{price_to*100}
          &attributesByKey[]=constructionYear:{year_from}:{year_to}
      price open-ended → trailing empty ("PriceCents:N:")
  Listings  listings[].vipUrl ("/v/auto-s/…"), prefixed with the site origin and
            deduped within the page.
"""
from __future__ import annotations

from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

_SEARCH_URL = "https://www.marktplaats.nl/lrp/api/search"
_CARS_L1_CATEGORY = 91  # Auto's [ASSUMED — long-stable L1 category id]
_SITE_ORIGIN = "https://www.marktplaats.nl"


class MarktplaatsScraper(HttpPortalScraper):
    """marktplaats.nl cars scraper (curl_cffi tier, Cloudflare Pro, lrp JSON API)."""

    DOMAIN = "marktplaats.nl"
    COUNTRY = "NL"

    # The lrp API returns up to 30 listings/page and caps deep offsets, so a capped
    # price window is subdivided rather than paged past the ceiling. [ASSUMED]
    PAGE_SIZE = 30
    MAX_PAGES = 30

    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        offset = (page_num - 1) * self.PAGE_SIZE
        price_to = params["price_to"]
        # marktplaats price attributes are denominated in cents.
        price_cents = f"{params['price_from'] * 100}:{'' if price_to is None else price_to * 100}"
        year = f"{params['year_from']}:{params['year_to']}"
        url = (
            f"{_SEARCH_URL}?l1CategoryId={_CARS_L1_CATEGORY}"
            f"&offset={offset}&limit={self.PAGE_SIZE}"
            f"&attributesByKey[]=PriceCents:{price_cents}"
            f"&attributesByKey[]=constructionYear:{year}"
        )
        return PortalRequest(url=url)

    def _extract(self, response: Any) -> list[str]:
        """Pull `listings[].vipUrl` from the JSON, prefixed + deduped within the page."""
        payload = self._response_json(response)
        if not isinstance(payload, dict):
            return []
        listings = payload.get("listings")
        if not isinstance(listings, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for listing in listings:
            if not isinstance(listing, dict):
                continue
            vip = listing.get("vipUrl")
            if not isinstance(vip, str) or not vip:
                continue
            full = vip if vip.startswith("http") else f"{_SITE_ORIGIN}{vip}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out
