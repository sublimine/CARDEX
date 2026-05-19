"""
WAF classifier — detecta qué protección tiene un dominio nuevo.

Usado para dominios que no están en DOMAIN_TIER_REGISTRY (dealers individuales).
La clasificación se persiste en engine.db domain_tier_state y no se repite
hasta que schema_fp cambie o forced=True.

Protocolo (SCRAPING_ENGINE.md §D1):
  1. HEAD sin proxy → 403 inmediato → waf_active=high
  2. GET con curl_cffi → analizar headers:
     CF-Ray        → Cloudflare (determinar nivel por response)
     x-datadome-*  → DataDome → T3
     ak_bmsc cookie → Akamai confirmado → T2
     "Just a moment" en body → CF challenge → T2
  3. Registrar resultado en domain_tier_state
  4. Asignar tier conservador (mejor sobre-proteger que sub-proteger)
"""
from __future__ import annotations

import sqlite3

from scrapers.engine.router.domain_map import Tier, WAF, PortalSpec


async def classify(domain: str, proxy_url: str | None = None) -> PortalSpec:
    """
    Classify a new domain. Returns PortalSpec with detected tier and WAF.
    Runs 2-step probe (HEAD + GET). Takes ~2-5s.
    """
    raise NotImplementedError


def persist(conn: sqlite3.Connection, spec: PortalSpec) -> None:
    """Save classification to domain_tier_state. Updates verified_at."""
    raise NotImplementedError


def is_stale(conn: sqlite3.Connection, domain: str, max_age_days: int = 7) -> bool:
    """True if classification is older than max_age_days or missing."""
    raise NotImplementedError
