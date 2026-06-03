"""
leboncoin.fr scraper — the finder JSON API behind DataDome (Tier.T3).

LeBonCoin's web/mobile front-ends both read from a JSON search API rather than
rendering listings server-side, so the cheapest correct path is to POST the same
query the site does and read deep links straight out of the JSON. The site sits
behind DataDome, which is why domain_map routes leboncoin.fr to T3 (behavioral +
residential): the request still has to look human, but the *response parsing* is
trivial JSON, not HTML scraping.

Request shape [ASSUMED — endpoint + payload inferred from the documented
finder/search contract and the public web `api_key`; not re-verified live this
cycle. The cars category id "2" is the long-stable LeBonCoin value]:

  POST https://api.leboncoin.fr/finder/search
  headers  api_key + Content-Type + Origin/Referer (https://www.leboncoin.fr)
  body     filters.category.id = "2"            (Voitures / cars)
           filters.ranges.regdate = {min,max}   (first-registration year)
           filters.ranges.price   = {min,max}   (price; open-ended → max omitted)
           limit = PAGE_SIZE, offset = (page-1)*PAGE_SIZE, sort_by time desc
  response {"ads": [{"url": "https://www.leboncoin.fr/…/{id}.htm", …}], "total": N}

DataDome soft-block: a challenged request is a 403 (handled by base
BLOCK_STATUSES) or a body carrying captcha-delivery.com, which the base
WAF-classifier already flags — no override needed here.
"""
from __future__ import annotations

from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

# Public web api_key used by the leboncoin.fr front-end for the finder API. [ASSUMED]
_API_KEY = "ba0c2dad52b3ec"
_SEARCH_URL = "https://api.leboncoin.fr/finder/search"
_CARS_CATEGORY_ID = "2"  # Voitures [ASSUMED — long-stable category id]


class LeBonCoinScraper(HttpPortalScraper):
    """leboncoin.fr cars scraper (DataDome tier, JSON finder API)."""

    DOMAIN = "leboncoin.fr"
    COUNTRY = "FR"

    # The finder API returns up to 35 ads/page; LeBonCoin caps deep pagination, so
    # a capped price window is subdivided rather than paged past the ceiling. [ASSUMED]
    PAGE_SIZE = 35
    MAX_PAGES = 100

    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        price: dict[str, int] = {"min": params["price_from"]}
        if params["price_to"] is not None:
            price["max"] = params["price_to"]
        body = {
            "filters": {
                "category": {"id": _CARS_CATEGORY_ID},
                "enums": {"ad_type": ["offer"]},
                "ranges": {
                    "regdate": {"min": params["year_from"], "max": params["year_to"]},
                    "price": price,
                },
            },
            "limit": self.PAGE_SIZE,
            "limit_alu": 0,
            "offset": (page_num - 1) * self.PAGE_SIZE,
            "sort_by": "time",
            "sort_order": "desc",
        }
        headers = {
            "api_key": _API_KEY,
            "Content-Type": "application/json",
            "Origin": "https://www.leboncoin.fr",
            "Referer": "https://www.leboncoin.fr/",
        }
        return PortalRequest(url=_SEARCH_URL, method="POST", json_body=body, headers=headers)

    def _extract(self, response: Any) -> list[str]:
        """Pull `ads[].url` from the JSON, deduped within the page."""
        payload = self._response_json(response)
        if not isinstance(payload, dict):
            return []
        ads = payload.get("ads")
        if not isinstance(ads, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for ad in ads:
            if not isinstance(ad, dict):
                continue
            url = ad.get("url")
            if isinstance(url, str) and url and url not in seen:
                seen.add(url)
                out.append(url)
        return out
