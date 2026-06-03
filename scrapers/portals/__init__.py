"""
Portal registry — domain → scraper class for every onboarded portal.

`get_scraper(domain)` is the coordinator's single resolution point: it maps a
work_queue row's `portal` to a fresh scraper instance, or None when the domain
has no scraper (a misconfiguration the coordinator records as terminal rather
than retrying forever). The registry is keyed by each scraper's own DOMAIN, so
onboarding a portal is one tuple entry here plus its module — no string drift
between the class and its lookup key.
"""
from __future__ import annotations

from scrapers.portals.base import BasePortalScraper
from scrapers.portals.be import AutoScout24BE
from scrapers.portals.ch import AutoScout24CH
from scrapers.portals.cochesnet import CochesNetScraper
from scrapers.portals.de import AutoScout24DE
from scrapers.portals.es import AutoScout24ES
from scrapers.portals.fr import AutoScout24FR
from scrapers.portals.kleinanzeigen import KleinanzeigenScraper
from scrapers.portals.lacentrale import LaCentraleScraper
from scrapers.portals.leboncoin import LeBonCoinScraper
from scrapers.portals.marktplaats import MarktplaatsScraper
from scrapers.portals.mobile_de import MobileDeScraper
from scrapers.portals.nl import AutoScout24NL

# Every concrete scraper the engine can dispatch. DOMAIN is the registry key.
_PORTAL_CLASSES: tuple[type[BasePortalScraper], ...] = (
    AutoScout24DE,
    AutoScout24FR,
    AutoScout24ES,
    AutoScout24NL,
    AutoScout24BE,
    AutoScout24CH,
    MobileDeScraper,
    LeBonCoinScraper,
    KleinanzeigenScraper,
    CochesNetScraper,
    MarktplaatsScraper,
    LaCentraleScraper,
)

PORTAL_REGISTRY: dict[str, type[BasePortalScraper]] = {
    cls.DOMAIN: cls for cls in _PORTAL_CLASSES
}


def get_scraper(domain: str) -> BasePortalScraper | None:
    """Return a fresh scraper instance for `domain`, or None if unregistered."""
    cls = PORTAL_REGISTRY.get(domain)
    return cls() if cls is not None else None
