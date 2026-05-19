"""
Proxy tier definitions — qué tier asignar según el portal.

Regla: el tier del proxy debe ser >= el tier del portal.
  T1 portal → ISP_STICKY suficiente
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


_PORTAL_TIER_TO_PROXY_TIER: dict[Tier, ProxyTier] = {
    Tier.T0: ProxyTier.ISP_STICKY,
    Tier.T1: ProxyTier.ISP_STICKY,
    Tier.T2: ProxyTier.ISP_STICKY,
    Tier.T3: ProxyTier.RESIDENTIAL_ROTATING,
}


def required_proxy_tier(portal_tier: Tier) -> ProxyTier:
    return _PORTAL_TIER_TO_PROXY_TIER[portal_tier]


def provider_for(proxy_tier: ProxyTier, country: str) -> str:
    """Return primary provider name for (proxy_tier, country)."""
    if proxy_tier == ProxyTier.RESIDENTIAL_ROTATING and country == "FR":
        return "bright_data"     # mejor pool FR
    if proxy_tier == ProxyTier.RESIDENTIAL_ROTATING:
        return "oxylabs"
    if proxy_tier == ProxyTier.MOBILE:
        return "decodo_mobile"
    return "decodo"
