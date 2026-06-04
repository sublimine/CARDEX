"""
Portal registry — domain -> scraper class for every onboarded portal.

`get_scraper(domain)` is the coordinator's single resolution point: it maps a
work_queue row's `portal` to a fresh scraper instance, or None when the domain
has no scraper (a misconfiguration the coordinator records as terminal rather
than retrying forever). The registry is keyed by each scraper's own DOMAIN, so
onboarding a portal is one tuple entry here plus its module -- no string drift
between the class and its lookup key.
"""
from __future__ import annotations

from scrapers.portals.autocasion_com import AutocasionESScraper
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
from scrapers.portals.anibis_ch import AnibisCHScraper
from scrapers.portals.autolina_ch import AutolinaCHScraper
from scrapers.portals.tutti_ch import TuttiCHScraper
from scrapers.portals.tweedehands_be import TweedehandsBEScraper
from scrapers.portals.viabovag_nl import ViaBovagNLScraper
from scrapers.portals.ocasionplus_es import OcasionPlusESScraper
from scrapers.portals.autokopen_nl import AutoKopenNLScraper
from scrapers.portals.nederlandmobiel_nl import NederlandMobielNLScraper
from scrapers.portals.autoboerse_de import AutoboerseDEScraper
from scrapers.portals.carvago_com import CarvagoCOMScraper
from scrapers.portals.deuxememain_be import DeuxememainBEScraper
from scrapers.portals.cardoen_be import CardoenBEScraper
from scrapers.portals.aramisauto_fr import AramisAutoFRScraper
from scrapers.portals.leparking_fr import LeParkingFRScraper
from scrapers.portals.autosphere_fr import AutosphereFRScraper
from scrapers.portals.reezocar_fr import ReezocarFRScraper
from scrapers.portals.spoticar_fr import SpoticarFRScraper
from scrapers.portals.auto_selection_com import AutoSelectionFRScraper
from scrapers.portals.annonces_automobile_com import AnnoncesAutomobileFRScraper
from scrapers.portals.starterre_fr import StarterreFRScraper
from scrapers.portals.carizy_com import CarizyFRScraper
from scrapers.portals.moniteur_auto_be import MoniteurAutoBEScraper

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
    # Phase 3 portals -- Tier-0/Tier-1 high-volume targets
    ParuVenduFRScraper,
    LargusFRScraper,
    AutoTrackNLScraper,
    GaspedaalNLScraper,
    MotorESScraper,
    AutocasionESScraper,
    # Phase 5 portals
    TweedehandsBEScraper,
    ViaBovagNLScraper,
    TuttiCHScraper,
    AnibisCHScraper,
    AutolinaCHScraper,
    # Phase 6 portals -- ES/NL expansion
    OcasionPlusESScraper,
    AutoKopenNLScraper,
    NederlandMobielNLScraper,
    # Phase 6 portals -- DE/CH expansion
    AutoboerseDEScraper,
    CarvagoCOMScraper,
    # Phase 6 portals -- FR/BE expansion
    DeuxememainBEScraper,
    CardoenBEScraper,
    AramisAutoFRScraper,
    LeParkingFRScraper,
    AutosphereFRScraper,
    ReezocarFRScraper,
    SpoticarFRScraper,
    AutoSelectionFRScraper,
    AnnoncesAutomobileFRScraper,
    StarterreFRScraper,
    CarizyFRScraper,
    MoniteurAutoBEScraper,
)

PORTAL_REGISTRY: dict[str, type[BasePortalScraper]] = {
    cls.DOMAIN: cls for cls in _PORTAL_CLASSES
}


def get_scraper(domain: str) -> BasePortalScraper | None:
    """Return a fresh scraper instance for domain, or None if unregistered."""
    cls = PORTAL_REGISTRY.get(domain)
    return cls() if cls is not None else None
