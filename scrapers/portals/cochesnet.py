"""
coches.net scraper — the Adevinta JSON search API behind Cloudflare (Tier.T1→T2).

coches.net is an Adevinta/Schibsted property whose web front-end reads from a JSON
search service rather than rendering listings server-side, so the cheapest correct
path is to POST the same query the site does and read deep links out of the JSON.
domain_map routes coches.net to T1 (curl_cffi) with an escalation ceiling of T2
(Camoufox) behind Cloudflare Pro; a challenged request is the standard CF
interstitial the base WAF-classifier already flags, so no _is_soft_block override
is needed.

Request shape [ASSUMED — endpoint, payload and headers inferred from the Adevinta
"ms-mt" web-search contract shared across Schibsted marketplaces; NOT live-verified
against coches.net this cycle. Treat the whole request shape as assumed; the
`items[].url` / `.aspx` detail-link shape is the more stable part]:

  POST https://ms-mt--api-web.spain.advgo.net/search
  headers  Content-Type + X-Adevinta-Channel:web + X-Schibsted-Tenant:coches
           + Origin/Referer (https://www.coches.net)
  body     pagination {page, size}
           sort {order:"desc", term:"publishedDate"}
           filters categoryId=2 (cars) + price{from,to} + year{from,to}
                   price open-ended → "to" omitted
  response {"items": [{"url": "https://www.coches.net/…-{id}.aspx", …}], …}
"""
from __future__ import annotations

from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

_SEARCH_URL = "https://ms-mt--api-web.spain.advgo.net/search"  # [ASSUMED]
_CARS_CATEGORY_ID = 2  # [ASSUMED — Adevinta cars category id]


class CochesNetScraper(HttpPortalScraper):
    """coches.net cars scraper (curl_cffi→Camoufox tier, Cloudflare Pro, JSON API)."""

    DOMAIN = "coches.net"
    COUNTRY = "ES"

    # The Adevinta search API returns up to 30 items/page and caps deep pagination,
    # so a capped price window is subdivided rather than paged past the ceiling. [ASSUMED]
    PAGE_SIZE = 30
    MAX_PAGES = 50

    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        price: dict[str, int] = {"from": params["price_from"]}
        if params["price_to"] is not None:
            price["to"] = params["price_to"]
        body = {
            "pagination": {"page": page_num, "size": self.PAGE_SIZE},
            "sort": {"order": "desc", "term": "publishedDate"},
            "filters": {
                "categoryId": _CARS_CATEGORY_ID,
                "price": price,
                "year": {"from": params["year_from"], "to": params["year_to"]},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Adevinta-Channel": "web",
            "X-Schibsted-Tenant": "coches",
            "Origin": "https://www.coches.net",
            "Referer": "https://www.coches.net/",
        }
        return PortalRequest(url=_SEARCH_URL, method="POST", json_body=body, headers=headers)

    def _extract(self, response: Any) -> list[str]:
        """Pull `items[].url` from the JSON, deduped within the page."""
        payload = self._response_json(response)
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if isinstance(url, str) and url and url not in seen:
                seen.add(url)
                out.append(url)
        return out
