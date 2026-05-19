"""
Warming daemon — protocolo de 3 fases para nuevas identidades.

FASE 1 — Ambient (48h)
  Tráfico: 40-60 requests/día a news + search + sitios random por país.
  Sin visitas a portales objetivo.
  Objetivo: IP no parece fresca, patrón orgánico establecido.

FASE 2 — Portal familiarization (24h)
  Tráfico: homepage del portal objetivo + 1-2 categorías + 1-2 listings (sin extraer).
  Dwell real: 30-60s por página, scroll orgánico vía Intent Engine.
  Objetivo: cookies reales, primer _abck generado y persistido.

FASE 3 — Active (warming_done = True, trust_score >= 3.0)
  Extracción permitida. Intent Engine activo en cada sesión.

REGLA DURA: extracción antes de completar Fase 2 → identidad quemada, retire inmediato.
  No existe recovery para identidades que extrajeron sin warming.
"""
from __future__ import annotations

import asyncio
import sqlite3
import logging

from scrapers.common.pw_base import intercept_paginate, dom_paginate
from scrapers.engine.identity.profile import Identity
from scrapers.engine.session.state import load as load_state, save as save_state

log = logging.getLogger(__name__)

# Sitios de warming por país — tráfico orgánico plausible
_AMBIENT_SITES: dict[str, list[str]] = {
    "DE": ["https://www.spiegel.de", "https://www.zeit.de", "https://www.google.de"],
    "ES": ["https://www.elpais.com", "https://www.rtve.es", "https://www.google.es"],
    "FR": ["https://www.lemonde.fr", "https://www.lefigaro.fr", "https://www.google.fr"],
    "NL": ["https://www.nu.nl", "https://www.nos.nl", "https://www.google.nl"],
    "BE": ["https://www.rtbf.be", "https://www.lesoir.be", "https://www.google.be"],
    "CH": ["https://www.nzz.ch", "https://www.srf.ch", "https://www.google.ch"],
}


async def run_phase1(identity: Identity, conn: sqlite3.Connection) -> None:
    """
    48h ambient warming. Uses Camoufox with identity proxy.
    Writes progress to warming_schedule table.
    """
    raise NotImplementedError


async def run_phase2(identity: Identity, domain: str, conn: sqlite3.Connection) -> None:
    """
    24h portal familiarization. Uses Camoufox + Intent Engine.
    Persists storage_state + first _abck after completion.
    """
    raise NotImplementedError


def is_warming_complete(conn: sqlite3.Connection, identity_id: str, domain: str) -> bool:
    raise NotImplementedError


def enforce_no_extraction_before_warming(identity: Identity, domain: str) -> None:
    """Raise RuntimeError if extraction is attempted before warming_done=True."""
    if not identity.warming_done:
        raise RuntimeError(
            f"Identity {identity.id} attempted extraction on {domain} before warming. "
            "Retiring immediately. Do not use this identity again."
        )
