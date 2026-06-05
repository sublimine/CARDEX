"""
lacentrale.fr scraper — the HTML listing path behind DataDome (Tier.T3).

lacentrale.fr renders its used-car listing server-side, so the cheapest correct
path is a GET against the listing search page and a regex over the returned HTML
for detail deep links. domain_map routes it to T3 (behavioral + residential)
because the site sits behind DataDome: the request still has to look human, but the
*response parsing* is trivial HTML, not a JSON contract.

DataDome soft-block: a challenged request is a 403 (handled by base BLOCK_STATUSES)
or a 200 body carrying captcha-delivery.com, which the base WAF-classifier already
flags — no _is_soft_block override is needed here.

Search-grid → URL mapping [ASSUMED — query parameter names inferred from the
lacentrale.fr listing URL grammar (priceMin/priceMax, yearMin/yearMax, page); NOT
re-verified against live HTML this cycle. The `/auto-occasion-annonce-{id}.html`
detail-link shape is the stable, long-lived part]:

  Search URL  /listing?priceMin={price_from}&priceMax={price_to}
                  &yearMin={year_from}&yearMax={year_to}&page={n}
              price open-ended → priceMax omitted
  Listings    /auto-occasion-annonce-{digits}.html, extracted by regex over the
              HTML body (deep links, deduped within the page).
"""
from __future__ import annotations

import re
from functools import cached_property
from typing import Any

from scrapers.portals.http_base import HttpPortalScraper, PortalRequest

_SITE_ORIGIN = "https://www.lacentrale.fr"


class LaCentraleScraper(HttpPortalScraper):
    """lacentrale.fr cars scraper (DataDome tier, HTML listing page)."""

    DOMAIN = "lacentrale.fr"
    COUNTRY = "FR"

    # lacentrale paginates ~16 results/page and caps deep pagination, so a capped
    # price window is subdivided rather than paged past the ceiling. [ASSUMED]
    PAGE_SIZE = 16
    MAX_PAGES = 100

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/auto-occasion-annonce-{id}.html` deep links in the HTML body."""
        return re.compile(r"/auto-occasion-annonce-(\d+)\.html")

    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        price_to = params["price_to"]
        url = (
            f"{_SITE_ORIGIN}/listing"
            f"?priceMin={params['price_from']}"
        )
        if price_to is not None:
            url += f"&priceMax={price_to}"
        url += (
            f"&yearMin={params['year_from']}"
            f"&yearMax={params['year_to']}"
            f"&page={page_num}"
        )
        return PortalRequest(url=url)

    def _extract(self, response: Any) -> list[str]:
        """Pull `/auto-occasion-annonce-…` deep links from the HTML, deduped per page."""
        html = self._response_text(response)
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            full = f"{_SITE_ORIGIN}/auto-occasion-annonce-{match.group(1)}.html"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out
