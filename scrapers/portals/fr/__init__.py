"""AutoScout24 France — autoscout24.fr, deep links under /annonces/."""
from __future__ import annotations

from scrapers.portals.autoscout24_base import AutoScout24Scraper


class AutoScout24FR(AutoScout24Scraper):
    DOMAIN = "autoscout24.fr"
    COUNTRY = "FR"
    HOST = "www.autoscout24.fr"
    LISTING_PREFIXES = ("/annonces/",)
