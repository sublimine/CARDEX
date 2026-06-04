"""
Portal registry -- domain -> scraper class for every onboarded portal.

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
from scrapers.portals.flexicar_es import FlexicarESScraper
from scrapers.portals.clicars_com import ClicarsESScraper
from scrapers.portals.autowereld_nl import AutowereldNLScraper
from scrapers.portals.auto_de import AutoDEScraper
from scrapers.portals.youcar_be import YoucarBEScraper
from scrapers.portals.myway_be import MyWayBEScraper
from scrapers.portals.capcar_fr import CapCarFRScraper
from scrapers.portals.pkw_de import PkwDEScraper
from scrapers.portals.autohaus24_de import Autohaus24DEScraper
from scrapers.portals.autohus_de import AutohusDEScraper
from scrapers.portals.buscocoches_com import BuscocochesESScraper
from scrapers.portals.belgiemobiel_be import BelgieMobielBEScraper
from scrapers.portals.vroom_be import VroomBEScraper
from scrapers.portals.carforyou_ch import CarForYouCHScraper
from scrapers.portals.jeanlain_fr import JeanLainFRScraper
from scrapers.portals.gowago_ch import GowagoCHScraper
from scrapers.portals.gueudet_fr import GueudetFRScraper
from scrapers.portals.comparis_ch import ComparisCHScraper
from scrapers.portals.distinxion_fr import DistinxionFRScraper
from scrapers.portals.wallapop_com import WallapopComScraper
from scrapers.portals.autohero_com import AutoheroCOMScraper
from scrapers.portals.heycar_com import HeycarFRScraper
from scrapers.portals.gocar_be import GocarBEScraper
from scrapers.portals.milanuncios_com import MilanunciosESScraper
from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
from scrapers.portals.coches_com import CochesComESScraper

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
    # Phase 3 portals
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
    # Phase 7 portals -- remaining T0/T1 coverage
    FlexicarESScraper,
    ClicarsESScraper,
    AutowereldNLScraper,
    AutoDEScraper,
    YoucarBEScraper,
    MyWayBEScraper,
    CapCarFRScraper,
    # Phase 8 portals -- deep sweep
    PkwDEScraper,
    Autohaus24DEScraper,
    AutohusDEScraper,
    BuscocochesESScraper,
    BelgieMobielBEScraper,
    VroomBEScraper,
    CarForYouCHScraper,
    JeanLainFRScraper,
    # Phase 9 portals -- coverage gap closure
    GowagoCHScraper,
    GueudetFRScraper,
    DistinxionFRScraper,
    ComparisCHScraper,
    # Phase 10 portals -- T2 bypass (API/SSR without Camoufox)
    WallapopComScraper,
    AutoheroCOMScraper,
    HeycarFRScraper,
    # Phase 11 portals -- T2/T3 Camoufox SSR
    GocarBEScraper,
    MilanunciosESScraper,
    ZoomcarFRScraper,
    CochesComESScraper,
)

PORTAL_REGISTRY: dict[str, type[BasePortalScraper]] = {
    cls.DOMAIN: cls for cls in _PORTAL_CLASSES
}


def get_scraper(domain: str) -> BasePortalScraper | None:
    """Return a fresh scraper instance for domain, or None if unregistered."""
    cls = PORTAL_REGISTRY.get(domain)
    return cls() if cls is not None else None
