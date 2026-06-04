"""AutoScout24 Switzerland — autoscout24.ch, bilingual deep links (/annonces/ + /angebote/)."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24CH(AutoScout24Scraper):
    DOMAIN = "autoscout24.ch"
    COUNTRY = "CH"
    HOST = "www.autoscout24.ch"
    LISTING_PREFIXES = ("/annonces/", "/angebote/")
