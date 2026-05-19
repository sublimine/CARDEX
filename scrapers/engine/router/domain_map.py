"""
DOMAIN_TIER_REGISTRY — ground truth verificado de qué tier requiere cada portal.

T0: Mobile API directa — sin anti-bot web
T1: curl_cffi chrome136 — sin browser
T2: Camoufox + storageState + _abck — browser Firefox
T3: Camoufox + Oxymouse behavioral + CapSolver + residential — browser behavioral

Actualizar tras cada run de diag.py con resultado real.
Fuente de verdad: este archivo. No engine.db (ese es el estado runtime, este es el baseline).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class WAF(str, Enum):
    NONE = "none"
    CF_FREE = "cf_free"
    CF_PRO = "cf_pro"
    CF_BUSINESS = "cf_business"
    AKAMAI_V3 = "akamai_v3"
    DATADOME = "datadome"
    PERIMETER_X = "perimeter_x"
    UNKNOWN = "unknown"


@dataclass
class PortalSpec:
    domain_pattern: str        # e.g. "autoscout24.*" or "mobile.de"
    tier: Tier
    waf: WAF
    can_escalate_to: Tier | None = None
    countries: list[str] = field(default_factory=list)
    notes: str = ""


# Verified against production + diag.py (last check: 2026-05-07)
REGISTRY: list[PortalSpec] = [
    # T0 — Mobile API bypass
    PortalSpec("mobile.de",       Tier.T0, WAF.NONE,        countries=["DE"], notes="Ad-Stream WSS consumer"),

    # T1 — curl_cffi sufficient
    PortalSpec("kleinanzeigen.de",Tier.T1, WAF.CF_PRO,      countries=["DE"]),
    PortalSpec("tutti.ch",        Tier.T1, WAF.CF_FREE,     countries=["CH"]),
    PortalSpec("autotrack.nl",    Tier.T1, WAF.NONE,        countries=["NL"]),
    PortalSpec("gaspedaal.nl",    Tier.T1, WAF.NONE,        countries=["NL"]),
    PortalSpec("marktplaats.nl",  Tier.T1, WAF.CF_PRO,      countries=["NL"]),
    PortalSpec("paruvendu.fr",    Tier.T1, WAF.NONE,        countries=["FR"]),
    PortalSpec("largus.fr",       Tier.T1, WAF.NONE,        countries=["FR"]),
    PortalSpec("motor.es",        Tier.T1, WAF.NONE,        countries=["ES"]),
    PortalSpec("autocasion.com",  Tier.T1, WAF.CF_FREE,     countries=["ES"]),
    PortalSpec("tweedehands.be",  Tier.T0, WAF.NONE,        countries=["BE"], notes="API pública 2dehands"),

    # T1 → escalate T2
    PortalSpec("coches.net",      Tier.T1, WAF.CF_PRO,      can_escalate_to=Tier.T2, countries=["ES"]),
    PortalSpec("mobile.de",       Tier.T1, WAF.NONE,        can_escalate_to=Tier.T2, countries=["DE"]),

    # T2 — Camoufox required
    PortalSpec("autoscout24.*",   Tier.T2, WAF.AKAMAI_V3,   can_escalate_to=Tier.T3, countries=["DE","ES","FR","NL","BE","CH"]),
    PortalSpec("wallapop.com",    Tier.T2, WAF.PERIMETER_X, can_escalate_to=Tier.T3, countries=["ES"]),
    PortalSpec("gocar.be",        Tier.T2, WAF.CF_BUSINESS, countries=["BE"]),
    PortalSpec("comparis.ch",     Tier.T2, WAF.CF_BUSINESS, countries=["CH"]),
    PortalSpec("heycar.com",      Tier.T2, WAF.CF_PRO,      countries=["DE","FR"]),
    PortalSpec("autohero.com",    Tier.T2, WAF.CF_PRO,      countries=["DE"]),
    PortalSpec("ouestfrance-auto.fr", Tier.T2, WAF.CF_PRO,  countries=["FR"]),
    PortalSpec("coches.com",      Tier.T2, WAF.CF_PRO,      countries=["ES"]),

    # T3 — Behavioral required (DataDome + residential)
    PortalSpec("leboncoin.fr",    Tier.T3, WAF.DATADOME,    countries=["FR"]),
    PortalSpec("lacentrale.fr",   Tier.T3, WAF.DATADOME,    countries=["FR"]),
    PortalSpec("milanuncios.com", Tier.T3, WAF.DATADOME,    countries=["ES"]),
]


def get(domain: str) -> PortalSpec | None:
    """Match domain against registry. Supports wildcard patterns (e.g. autoscout24.*)."""
    raise NotImplementedError


def effective_tier(domain: str, circuit_state: dict) -> Tier:
    """
    Return the tier to use now, considering circuit breaker escalation.
    circuit_state: {(domain, tier): 'open'|'closed'|'half_open'}
    """
    raise NotImplementedError
