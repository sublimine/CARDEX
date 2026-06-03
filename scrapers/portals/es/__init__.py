"""AutoScout24 Spain — autoscout24.es, deep links under /anuncios/."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24ES(AutoScout24Scraper):
    DOMAIN = "autoscout24.es"
    COUNTRY = "ES"
    HOST = "www.autoscout24.es"
    LISTING_PREFIXES = ("/anuncios/",)
