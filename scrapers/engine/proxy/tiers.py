"""
Proxy tier definitions — qué tier asignar según el portal.

Direct-first policy (T0/T1):
  T0/T1 portals carry NO anti-bot WAF (open JSON/mobile APIs, plain curl_cffi
  SSR). They run direct — no proxy — with UA rotation only; a residential IP buys
  nothing there. `allows_direct`/`requires_proxy` express that: T0/T1 accept a
  DIRECT identity, T2/T3 do not. `required_proxy_tier` stays the proxy-fallback
  map (the tier to use IF a proxy is ever attached — e.g. T0/T1 escalation or a
  future block), so it still answers ISP_STICKY for T0/T1.

Proxy tiers (T2/T3 and fallback):
  T2 portal → ISP_STICKY (mínimo) o RESIDENTIAL_ROTATING
  T3 portal → RESIDENTIAL_ROTATING obligatorio (DataDome necesita IP residencial)

Providers por tier:
  ISP_STICKY:           Decodo (primary), IPRoyal Static (fallback)
  RESIDENTIAL_ROTATING: Oxylabs (primary), Bright Data (fallback para FR)
  MOBILE:               Decodo Mobile (emergencia — ASN datacenter bloqueado)
"""
from __future__ import annotations

from scrapers.engine.identity.profile import ProxyTier
from scrapers.engine.router.domain_map import Tier


# Portal tiers that may run on a DIRECT (no-proxy) identity — no anti-bot WAF.
_DIRECT_OK_TIERS: frozenset[Tier] = frozenset({Tier.T0, Tier.T1})

_PORTAL_TIER_TO_PROXY_TIER: dict[Tier, ProxyTier] = {
    Tier.T0: ProxyTier.ISP_STICKY,
    Tier.T1: ProxyTier.ISP_STICKY,
    Tier.T2: ProxyTier.ISP_STICKY,
    Tier.T3: ProxyTier.RESIDENTIAL_ROTATING,
}


def required_proxy_tier(portal_tier: Tier) -> ProxyTier:
    """Proxy tier to use IF a proxy is attached to this portal (fallback map)."""
    return _PORTAL_TIER_TO_PROXY_TIER[portal_tier]


def allows_direct(portal_tier: Tier) -> bool:
    """True when a DIRECT (no-proxy) identity is acceptable for this portal tier."""
    return portal_tier in _DIRECT_OK_TIERS


def requires_proxy(portal_tier: Tier) -> bool:
    """True when this portal tier (T2/T3) must use a proxied identity."""
    return not allows_direct(portal_tier)


def provider_for(proxy_tier: ProxyTier, country: str) -> str:
    """Return primary provider name for (proxy_tier, country)."""
    if proxy_tier == ProxyTier.RESIDENTIAL_ROTATING and country == "FR":
        return "bright_data"     # mejor pool FR
    if proxy_tier == ProxyTier.RESIDENTIAL_ROTATING:
        return "oxylabs"
    if proxy_tier == ProxyTier.MOBILE:
        return "decodo_mobile"
    return "decodo"
