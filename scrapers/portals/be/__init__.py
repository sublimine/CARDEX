"""AutoScout24 Belgium — autoscout24.be, bilingual deep links (/annonces/ + /aanbod/)."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24BE(AutoScout24Scraper):
    DOMAIN = "autoscout24.be"
    COUNTRY = "BE"
    HOST = "www.autoscout24.be"
    LISTING_PREFIXES = ("/annonces/", "/aanbod/")
