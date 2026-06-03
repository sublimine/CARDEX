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

from scrapers.portals.autotrack_nl import AutoTrackNLScraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.be import AutoScout24BE
from scrapers.portals.ch import AutoScout24CH
from scrapers.portals.coches_net import CochesNetScraper
from scrapers.portals.de import AutoScout24DE
from scrapers.portals.es import AutoScout24ES
from scrapers.portals.fr import AutoScout24FR
from scrapers.portals.gaspedaal_nl import GaspedaalNLScraper
from scrapers.portals.kleinanzeigen_de import KleinanzeigenDEScraper
from scrapers.portals.lacentrale_fr import LaCentraleFRScraper
from scrapers.portals.largus_fr import LargusFRScraper
from scrapers.portals.leboncoin_fr import LeboncoinFRScraper
from scrapers.portals.marktplaats_nl import MarktplaatsNLScraper
from scrapers.portals.mobile_de import MobileDeScraper
from scrapers.portals.motor_es import MotorESScraper
from scrapers.portals.nl import AutoScout24NL
from scrapers.portals.paruvendu_fr import ParuVenduFRScraper

# Every concrete scraper the engine can dispatch. DOMAIN is the registry key.
_PORTAL_CLASSES: tuple[type[BasePortalScraper], ...] = (
    # AutoScout24 family (Phase 1)
    AutoScout24DE,
    AutoScout24FR,
    AutoScout24ES,
    AutoScout24NL,
    AutoScout24BE,
    AutoScout24CH,
    # Phase 2 portals
    MobileDeScraper,
    MarktplaatsNLScraper,
    LeboncoinFRScraper,
    KleinanzeigenDEScraper,
    CochesNetScraper,
    LaCentraleFRScraper,
    # Phase 3 portals — Tier-0/Tier-1 high-volume targets
    ParuVenduFRScraper,
    LargusFRScraper,
    AutoTrackNLScraper,
    GaspedaalNLScraper,
    MotorESScraper,
)

PORTAL_REGISTRY: dict[str, type[BasePortalScraper]] = {
    cls.DOMAIN: cls for cls in _PORTAL_CLASSES
}


def get_scraper(domain: str) -> BasePortalScraper | None:
    """Return a fresh scraper instance for `domain`, or None if unregistered."""
    cls = PORTAL_REGISTRY.get(domain)
    return cls() if cls is not None else None
