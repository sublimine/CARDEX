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
    PortalSpec("marktplaats.nl", Tier.T0, WAF.NONE, countries=["NL"], notes="open LRP /lrp/api/search JSON; CloudFront, no WAF"),
    PortalSpec("2dehands.be", Tier.T0, WAF.NONE, countries=["BE"], notes="API LRP abierta /lrp/api/search JSON; CloudFront, sin WAF"),
    PortalSpec("tweedehands.be", Tier.T0, WAF.NONE, countries=["BE"], notes="alias de 2dehands.be"),
    PortalSpec("viabovag.nl", Tier.T1, WAF.NONE, countries=["NL"], notes="Next.js data route SSR, IIS, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("autolina.ch", Tier.T0, WAF.NONE, countries=["CH"], notes="API REST abierta m.autolina.ch, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("nederlandmobiel.nl", Tier.T0, WAF.NONE, countries=["NL"], notes="PHP SSR, ~313k auto listings, gratis platform, sin WAF [VERIFIED 2026-06-04]"),
    # T1 -- curl_cffi sufficient (Phase 6 DE/CH)
    PortalSpec("autoboerse.de", Tier.T1, WAF.NONE, countries=["DE"], notes="SSR HTML, ~250k Santander dealer listings [VERIFIED 2026-06-04]"),
    PortalSpec("carvago.com", Tier.T1, WAF.NONE, countries=["DE","CZ","EU"], notes="Next.js CSR, ~1.07M pan-European listings [VERIFIED 2026-06-04]"),
    # T1 -- curl_cffi sufficient
    PortalSpec("tutti.ch", Tier.T1, WAF.CF_FREE, countries=["CH"]),
    PortalSpec("anibis.ch", Tier.T1, WAF.CF_FREE, countries=["CH"], notes="gemelo FR de tutti.ch, mismo backend Scout24 [VERIFIED 2026-06-04]"),
    PortalSpec("autotrack.nl", Tier.T1, WAF.NONE, countries=["NL"]),
    PortalSpec("gaspedaal.nl", Tier.T1, WAF.NONE, countries=["NL"]),
    PortalSpec("paruvendu.fr", Tier.T1, WAF.NONE, countries=["FR"]),
    PortalSpec("largus.fr", Tier.T1, WAF.NONE, countries=["FR"]),
    PortalSpec("motor.es", Tier.T1, WAF.NONE, countries=["ES"]),
    PortalSpec("autocasion.com", Tier.T1, WAF.CF_FREE, countries=["ES"]),
    PortalSpec("ocasionplus.com", Tier.T1, WAF.NONE, countries=["ES"], notes="Next.js SSR, ~20k listings, sin WAF [VERIFIED 2026-06-04]"),
    PortalSpec("autokopen.nl", Tier.T1, WAF.NONE, countries=["NL"], notes="Next.js SSR, ~106k listings [VERIFIED 2026-06-04]"),
    # T0 -- Phase 6 FR/BE expansion
    PortalSpec("2ememain.be", Tier.T0, WAF.NONE, countries=["BE"], notes="LRP API francophone mirror of 2dehands.be [VERIFIED 2026-06-04]"),
    PortalSpec("autosphere.fr", Tier.T0, WAF.NONE, countries=["FR"], notes="API REST /api/stock/vehicles, Next.js, ~15.6k VO [VERIFIED 2026-06-04]"),
    PortalSpec("auto-selection.com", Tier.T0, WAF.NONE, countries=["FR"], notes="Meilisearch public API, ~113k annonces [VERIFIED 2026-06-04]"),
    # T1 -- Phase 6 FR/BE expansion
    PortalSpec("cardoen.be", Tier.T1, WAF.CF_FREE, countries=["BE"], notes="SSR, ~850 VO, Cloudflare CDN [VERIFIED 2026-06-04]"),
    PortalSpec("aramisauto.com", Tier.T1, WAF.CF_FREE, countries=["FR"], notes="Next.js SSR, ~3k VO [VERIFIED 2026-06-04]"),
    PortalSpec("leparking.fr", Tier.T1, WAF.NONE, countries=["FR"], notes="meta-agregateur SSR HTML, ~14.8M annonces [VERIFIED 2026-06-04]"),
    PortalSpec("reezocar.com", Tier.T1, WAF.NONE, countries=["FR"], notes="agregateur europeen SSR [VERIFIED 2026-06-04]"),
    PortalSpec("spoticar.fr", Tier.T1, WAF.CF_FREE, countries=["FR"], notes="Stellantis network, ~80k VO [VERIFIED 2026-06-04]"),
    PortalSpec("annonces-automobile.com", Tier.T1, WAF.NONE, countries=["FR"], notes="SSR HTML jQuery, ~43k annonces [VERIFIED 2026-06-04]"),
    PortalSpec("starterre.fr", Tier.T1, WAF.NONE, countries=["FR"], notes="SSR HTML jQuery, ~7.3k mandataire [VERIFIED 2026-06-04]"),
    PortalSpec("carizy.com", Tier.T1, WAF.NONE, countries=["FR"], notes="Nuxt.js SSR, ~1.2k P2P [VERIFIED 2026-06-04]"),
    PortalSpec("moniteurautomobile.be", Tier.T1, WAF.NONE, countries=["BE"], notes="SSR HTML, ~120k annonces [VERIFIED 2026-06-04]"),
    # T1 -- Phase 7 remaining portals
    PortalSpec("flexicar.es", Tier.T1, WAF.UNKNOWN, countries=["ES"], notes="SSR HTML, ~25k vehicles [VERIFIED 2026-06-04]"),
    PortalSpec("clicars.com", Tier.T1, WAF.UNKNOWN, countries=["ES"], notes="SSR HTML, ~2k+ stock [VERIFIED 2026-06-04]"),
    PortalSpec("autowereld.nl", Tier.T1, WAF.UNKNOWN, countries=["NL"], notes="PHP SSR, ~270k occasions [VERIFIED 2026-06-04]"),
    PortalSpec("auto.de", Tier.T1, WAF.NONE, countries=["DE"], notes="WordPress, UUID vehicle IDs [VERIFIED 2026-06-04]"),
    PortalSpec("youcar.be", Tier.T1, WAF.UNKNOWN, countries=["BE"], notes="SSR HTML, NL/FR/EN [VERIFIED 2026-06-04]"),
    PortalSpec("myway.be", Tier.T1, WAF.UNKNOWN, countries=["BE"], notes="D'Ieteren certified [VERIFIED 2026-06-04]"),
    PortalSpec("capcar.fr", Tier.T1, WAF.UNKNOWN, countries=["FR"], notes="P2P with 350+ agents [VERIFIED 2026-06-04]"),
    # Phase 8 portals -- deep sweep
    PortalSpec("pkw.de", Tier.T1, WAF.UNKNOWN, countries=["DE"], notes="SSR HTML, multi-dealer marketplace [VERIFIED 2026-06-04]"),
    PortalSpec("autohaus24.de", Tier.T1, WAF.UNKNOWN, countries=["DE"], notes="Allane SE dealer, ~1000 vehicles [VERIFIED 2026-06-04]"),
    PortalSpec("autohus.de", Tier.T1, WAF.UNKNOWN, countries=["DE"], notes="DAT AUTOHUS AG, ~3000 vehicles [VERIFIED 2026-06-04]"),
    PortalSpec("buscocoches.com", Tier.T1, WAF.UNKNOWN, countries=["ES"], notes="National classifieds [VERIFIED 2026-06-04]"),
    PortalSpec("belgiemobiel.be", Tier.T1, WAF.NONE, countries=["BE"], notes="PHP SSR, ~20k auto listings [VERIFIED 2026-06-04]"),
    PortalSpec("vroom.be", Tier.T1, WAF.UNKNOWN, countries=["BE"], notes="Rossel/Roularta JV, ~40k cars [VERIFIED 2026-06-04]"),
    PortalSpec("carforyou.ch", Tier.T1, WAF.UNKNOWN, countries=["CH"], notes="#3 CH vehicles, ~966k visits [VERIFIED 2026-06-04]"),
    PortalSpec("occasions.jeanlain.com", Tier.T1, WAF.UNKNOWN, countries=["FR"], notes="Jean Lain, ~1800 vehicles [VERIFIED 2026-06-04]"),
    # Phase 9 portals -- coverage gap closure
    PortalSpec("gowago.ch", Tier.T1, WAF.NONE, countries=["CH"], notes="Swiss leasing marketplace, ~10k used cars, Next.js SSR [VERIFIED 2026-06-04]"),
    PortalSpec("gueudet.fr", Tier.T1, WAF.NONE, countries=["FR"], notes="Gueudet 1880 dealer group, ~5.2k VO, SSR HTML [VERIFIED 2026-06-04]"),
    PortalSpec("distinxion.fr", Tier.T1, WAF.NONE, countries=["FR"], notes="120+ POS network, ~1.6k VO, Symfony SSR [VERIFIED 2026-06-04]"),
    # T1 -> escalate T2
    PortalSpec("coches.net", Tier.T1, WAF.NONE, can_escalate_to=Tier.T2, countries=["ES"]),
    # T2 -- Camoufox / stealth browser required
    PortalSpec("mobile.de", Tier.T2, WAF.AKAMAI_V3, can_escalate_to=Tier.T3, countries=["DE"]),
    PortalSpec("kleinanzeigen.de", Tier.T2, WAF.AKAMAI_V3, can_escalate_to=Tier.T3, countries=["DE"]),
    PortalSpec("autoscout24.*", Tier.T2, WAF.AKAMAI_V3, can_escalate_to=Tier.T3, countries=["DE","ES","FR","NL","BE","CH"]),
    PortalSpec("wallapop.com", Tier.T0, WAF.PERIMETER_X, countries=["ES"], notes="T2->T0 bypass: mobile API api.wallapop.com/api/v3 bypasses PerimeterX [VERIFIED 2026-06-04]"),
    PortalSpec("gocar.be", Tier.T2, WAF.CF_BUSINESS, countries=["BE"]),
    PortalSpec("comparis.ch", Tier.T1, WAF.NONE, countries=["CH"], notes="T2->T1 bypass: SSR HTML no WAF, meta-aggregator ~214k listings [VERIFIED 2026-06-04]"),
    PortalSpec("autohero.com", Tier.T0, WAF.NONE, countries=["DE","IT","FR","ES","AT","PL","NL","SE"], notes="T2->T0 bypass: GraphQL API /v1/retail-customer-gateway/graphql/ no auth [VERIFIED 2026-06-04]"),
    PortalSpec("heycar.com", Tier.T0, WAF.NONE, countries=["FR"], notes="T2->T0 bypass: REST API api.fr.prod.group-mobility-trader.com no auth, DE dead [VERIFIED 2026-06-04]"),
    PortalSpec("ouestfrance-auto.fr", Tier.T2, WAF.CF_PRO, countries=["FR"]),
    PortalSpec("zoomcar.fr", Tier.T2, WAF.CF_PRO, countries=["FR"], notes="ex-ouestfrance-auto.com [VERIFIED 2026-06-04]"),
    PortalSpec("coches.com", Tier.T2, WAF.CF_PRO, countries=["ES"]),
    PortalSpec("autoweek.nl", Tier.T2, WAF.AKAMAI_V3, countries=["NL"], notes="DPG Media, syndication mirror of autotrack.nl via MediaVentions JV, ~187k listings [VERIFIED 2026-06-04]"),
    # Phase 12 -- newly discovered dealer networks
    PortalSpec("caravenue.com", Tier.T0, WAF.NONE, countries=["FR","BE","LU","CH"], notes="Next.js, 62-dealership group, ~2.4k vehicles [VERIFIED 2026-06-04]"),
    PortalSpec("simplicicar.com", Tier.T1, WAF.NONE, countries=["FR","BE"], notes="PrestaShop, 100+ POS franchise, ~6k vehicles [VERIFIED 2026-06-04]"),
    # Phase 13 -- commercial & niche specialist
    PortalSpec("truckscout24.com", Tier.T1, WAF.NONE, countries=["DE","EU"], notes="Yii2/PHP, AS24 Group commercial vehicles, ~80-120k listings [VERIFIED 2026-06-04]"),
    PortalSpec("classic-trader.com", Tier.T1, WAF.NONE, countries=["DE","EU"], notes="Astro SSR, luxury/classic marketplace, ~8.5k listings [VERIFIED 2026-06-04]"),
    # T3 -- Behavioral required (DataDome + residential)
    PortalSpec("leboncoin.fr", Tier.T3, WAF.DATADOME, countries=["FR"]),
    PortalSpec("lacentrale.fr", Tier.T3, WAF.DATADOME, countries=["FR"]),
    PortalSpec("milanuncios.com", Tier.T3, WAF.DATADOME, countries=["ES"]),
    PortalSpec("promoneuve.fr", Tier.T3, WAF.DATADOME, countries=["FR"], notes="NEW CARS ONLY [VERIFIED 2026-06-04]"),
]


_TIER_ORDER: tuple[Tier, ...] = (Tier.T0, Tier.T1, Tier.T2, Tier.T3)
_DEFAULT_TIER = Tier.T1  # conservative-but-cheap baseline for unknown dealers


def _tier_index(tier: Tier) -> int:
    return _TIER_ORDER.index(tier)


@lru_cache(maxsize=256)
def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """
    Compile a registry pattern into a domain matcher.

    A literal '*' matches one-and-more dot-separated labels (used as a TLD wildcard,
    e.g. autoscout24.*). Optional leading subdomains are always allowed so
    'www.mobile.de' matches the pattern 'mobile.de'.
    """
    escaped = re.escape(pattern).replace(r"\*", r"[a-z0-9-]+(?:\.[a-z0-9-]+)*")
    return re.compile(rf"^(?:[a-z0-9-]+\.)*{escaped}$", re.IGNORECASE)


def get(domain: str) -> PortalSpec | None:
    """
    Match domain against the registry. Supports wildcard patterns (autoscout24.*).

    First match in REGISTRY order wins, so register a more-specific pattern
    before a broader wildcard (e.g. a concrete dealer host before autoscout24.*).
    """
    host = domain.strip().lower()
    for spec in REGISTRY:
        if _pattern_regex(spec.domain_pattern).match(host):
            return spec
    return None


def effective_tier(domain: str, circuit_state: dict) -> Tier:
    """
    Return the tier to use now, considering circuit breaker escalation.

    circuit_state: {(domain, tier): 'open'|'closed'|'half_open'} where tier may be a
    Tier or its string value. Walks up from the portal's baseline tier, skipping any
    tier whose breaker is OPEN, bounded by the registry escalation ceiling
    (can_escalate_to). Returns the baseline when no escalation is configured/possible.
    """
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

    current = baseline
    idx = _tier_index(current)
    ceil_idx = _tier_index(ceiling)
    while _is_open(current) and idx < ceil_idx:
        idx += 1
        current = _TIER_ORDER[idx]
    return current
