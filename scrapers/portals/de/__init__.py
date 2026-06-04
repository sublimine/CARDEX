"""AutoScout24 Germany — autoscout24.de, deep links under /angebote/."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24DE(AutoScout24Scraper):
    DOMAIN = "autoscout24.de"
    COUNTRY = "DE"
    HOST = "www.autoscout24.de"
    LISTING_PREFIXES = ("/angebote/",)
