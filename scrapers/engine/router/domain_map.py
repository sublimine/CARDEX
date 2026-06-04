"""
DOMAIN_TIER_REGISTRY -- ground truth verificado de que tier requiere cada portal.

T0: Mobile API directa -- sin anti-bot web
T1: curl_cffi chrome136 -- sin browser
T2: Camoufox + storageState + _abck -- browser Firefox
T3: Camoufox + Oxymouse behavioral + CapSolver + residential -- browser behavioral

Actualizar tras cada run de diag.py con resultado real.
Fuente de verdad: este archivo. No engine.db (ese es el estado runtime, este es el baseline).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


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
    domain_pattern: str
    tier: Tier
    waf: WAF
    can_escalate_to: Tier | None = None
    countries: list[str] = field(default_factory=list)
    notes: str = ""


REGISTRY: list[PortalSpec] = [
    # T0 -- open JSON / mobile API, no anti-bot WAF
    PortalSpec("marktplaats.nl",  Tier.T0, WAF.NONE,        countries=["NL"], notes="open LRP /lrp/api/search JSON; CloudFront, no WAF"),
    PortalSpec("2dehands.be",     Tier.T0, WAF.NONE,        countries=["BE"], notes="API LRP abierta /lrp/api/search JSON; CloudFront, sin WAF"),
    PortalSpec("tweedehands.be",  Tier.T0, WAF.NONE,        countries=["BE"], notes="alias de 2dehands.be"),
    PortalSpec("viabovag.nl",     Tier.T1, WAF.NONE,        countries=["NL"], notes="Next.js data route SSR, IIS, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("autolina.ch",     Tier.T0, WAF.NONE,        countries=["CH"], notes="API REST abierta m.autolina.ch, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("nederlandmobiel.nl", Tier.T0, WAF.NONE,    countries=["NL"], notes="PHP SSR, ~313k auto listings, gratis platform, sin WAF [VERIFIED 2026-06-04]"),

    # T1 -- curl_cffi sufficient
    PortalSpec("tutti.ch",        Tier.T1, WAF.CF_FREE,     countries=["CH"]),
    PortalSpec("anibis.ch",       Tier.T1, WAF.CF_FREE,     countries=["CH"], notes="gemelo FR de tutti.ch, mismo backend Scout24 [VERIFIED 2026-06-04]"),
    PortalSpec("autotrack.nl",    Tier.T1, WAF.NONE,        countries=["NL"]),
    PortalSpec("gaspedaal.nl",    Tier.T1, WAF.NONE,        countries=["NL"]),
    PortalSpec("paruvendu.fr",    Tier.T1, WAF.NONE,        countries=["FR"]),
    PortalSpec("largus.fr",       Tier.T1, WAF.NONE,        countries=["FR"]),
    PortalSpec("motor.es",        Tier.T1, WAF.NONE,        countries=["ES"]),
    PortalSpec("autocasion.com",  Tier.T1, WAF.CF_FREE,     countries=["ES"]),
    PortalSpec("ocasionplus.com", Tier.T1, WAF.NONE,       countries=["ES"], notes="Next.js SSR, ~20k listings, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("autokopen.nl",   Tier.T1, WAF.NONE,        countries=["NL"], notes="Next.js SSR, ~106k listings, Dealerdirect Media, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("autowereld.nl",  Tier.T1, WAF.UNKNOWN,     countries=["NL"], notes="empty response on probe -- possible bot detection [2026-06-04]"),
    PortalSpec("flexicar.es",    Tier.T1, WAF.UNKNOWN,     countries=["ES"], notes="dealer chain, 25k+ vehicles, needs probe"),
    PortalSpec("clicars.com",    Tier.T1, WAF.UNKNOWN,     countries=["ES"], notes="online dealer platform, needs probe"),

    # T1 -> escalate T2
    PortalSpec("coches.net",      Tier.T1, WAF.NONE,        can_escalate_to=Tier.T2, countries=["ES"]),

    # T2 -- Camoufox / stealth browser required
    PortalSpec("mobile.de",       Tier.T2, WAF.AKAMAI_V3,   can_escalate_to=Tier.T3, countries=["DE"]),
    PortalSpec("kleinanzeigen.de",Tier.T2, WAF.AKAMAI_V3,   can_escalate_to=Tier.T3, countries=["DE"]),
    PortalSpec("autoscout24.*",   Tier.T2, WAF.AKAMAI_V3,   can_escalate_to=Tier.T3, countries=["DE","ES","FR","NL","BE","CH"]),
    PortalSpec("wallapop.com",    Tier.T2, WAF.PERIMETER_X, can_escalate_to=Tier.T3, countries=["ES"]),
    PortalSpec("gocar.be",        Tier.T2, WAF.CF_BUSINESS, countries=["BE"]),
    PortalSpec("comparis.ch",     Tier.T2, WAF.CF_BUSINESS, countries=["CH"]),
    PortalSpec("heycar.com",      Tier.T2, WAF.CF_PRO,      countries=["DE","FR"]),
    PortalSpec("autohero.com",    Tier.T2, WAF.CF_PRO,      countries=["DE"]),
    PortalSpec("ouestfrance-auto.fr", Tier.T2, WAF.CF_PRO,  countries=["FR"]),
    PortalSpec("coches.com",      Tier.T2, WAF.CF_PRO,      countries=["ES"]),
    PortalSpec("autoweek.nl",    Tier.T2, WAF.AKAMAI_V3,   countries=["NL"], notes="automotive media + classifieds, Akamai V3"),
    PortalSpec("coches.com",      Tier.T2, WAF.CF_PRO,      countries=["ES"]),

    # T3 -- Behavioral required (DataDome + residential)
    PortalSpec("leboncoin.fr",    Tier.T3, WAF.DATADOME,    countries=["FR"]),
    PortalSpec("lacentrale.fr",   Tier.T3, WAF.DATADOME,    countries=["FR"]),
    PortalSpec("milanuncios.com", Tier.T3, WAF.DATADOME,    countries=["ES"]),
]


_TIER_ORDER: tuple[Tier, ...] = (Tier.T0, Tier.T1, Tier.T2, Tier.T3)
_DEFAULT_TIER = Tier.T1


def _tier_index(tier: Tier) -> int:
    return _TIER_ORDER.index(tier)


@lru_cache(maxsize=256)
def _pattern_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern).replace(r"\*", r"[a-z0-9-]+(?:\.[a-z0-9-]+)*")
    return re.compile(rf"^(?:[a-z0-9-]+\.)*{escaped}$", re.IGNORECASE)


def get(domain: str) -> PortalSpec | None:
    host = domain.strip().lower()
    for spec in REGISTRY:
        if _pattern_regex(spec.domain_pattern).match(host):
            return spec
    return None


def effective_tier(domain: str, circuit_state: dict) -> Tier:
    spec = get(domain)
    baseline = spec.tier if spec else _DEFAULT_TIER
    if spec and spec.can_escalate_to is not None:
        ceiling = spec.can_escalate_to
    else:
        ceiling = baseline

    def _is_open(tier: Tier) -> bool:
        return (
            circuit_state.get((domain, tier)) == "open"
            or circuit_state.get((domain, tier.value)) == "open"
        )

  