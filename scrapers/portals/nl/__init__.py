"""AutoScout24 Netherlands — autoscout24.nl, deep links under /aanbod/."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24NL(AutoScout24Scraper):
    DOMAIN = "autoscout24.nl"
    COUNTRY = "NL"
    HOST = "www.autoscout24.nl"
    LISTING_PREFIXES = ("/aanbod/",)
