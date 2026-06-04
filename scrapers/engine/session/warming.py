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

import logging
import sqlite3
import time

from scrapers.engine.antidetect import behavioral
from scrapers.engine.antidetect.browser import proxy_dict_from_url
from scrapers.engine.identity.profile import Identity
from scrapers.engine.session import intent
from scrapers.engine.session.state import extract_abck, save as save_state

log = logging.getLogger(__name__)

# Phase numbers in warming_schedule.phase
PHASE_AMBIENT = 1
PHASE_PORTAL = 2

# Phase 1 is per-identity (no portal); a sentinel domain keys its schedule row.
_AMBIENT_DOMAIN = "_ambient"

# Completion targets (one warming session advances requests_done toward these;
# the scheduler invokes run_phaseN across the 48h/24h window until complete).
_PHASE1_TARGET = 50   # 40-60 organic req band, midpoint
_PHASE2_TARGET = 5    # homepage + categories + 1-2 listings

# _abck lifetime when first minted in phase 2 (~4h per Akamai Bot Manager v3).
_ABCK_TTL_S = 4 * 3600

# Sitios de warming por país — tráfico orgánico plausible
_AMBIENT_SITES: dict[str, list[str]] = {
    "DE": ["https://www.spiegel.de", "https://www.zeit.de", "https://www.google.de"],
    "ES": ["https://www.elpais.com", "https://www.rtve.es", "https://www.google.es"],
    "FR": ["https://www.lemonde.fr", "https://www.lefigaro.fr", "https://www.google.fr"],
    "NL": ["https://www.nu.nl", "https://www.nos.nl", "https://www.google.nl"],
    "BE": ["https://www.rtbf.be", "https://www.lesoir.be", "https://www.google.be"],
    "CH": ["https://www.nzz.ch", "https://www.srf.ch", "https://www.google.ch"],
}


# ── warming_schedule bookkeeping (pure DB, unit-tested) ───────────────────────

def _ensure_phase_row(
    conn: sqlite3.Connection, identity_id: str, domain: str, phase: int, target: int
) -> None:
    """Create the schedule row for (identity, domain, phase) if absent."""
    conn.execute(
        "INSERT OR IGNORE INTO warming_schedule "
        "(identity_id, target_domain, phase, requests_done, requests_target, started_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (identity_id, domain, phase, target, int(time.time())),
    )


def _phase_row(
    conn: sqlite3.Connection, identity_id: str, domain: str, phase: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT requests_done, requests_target, started_at, completed_at "
        "FROM warming_schedule WHERE identity_id = ? AND target_domain = ? AND phase = ?",
        (identity_id, domain, phase),
    ).fetchone()


def _record_progress(
    conn: sqlite3.Connection, identity_id: str, domain: str, phase: int, delta: int = 1
) -> None:
    """Increment requests_done and auto-complete once the target is reached."""
    conn.execute(
        "UPDATE warming_schedule SET requests_done = requests_done + ? "
        "WHERE identity_id = ? AND target_domain = ? AND phase = ?",
        (delta, identity_id, domain, phase),
    )
    row = _phase_row(conn, identity_id, domain, phase)
    if row is not None and row["completed_at"] is None and row["requests_done"] >= row["requests_target"]:
        _complete_phase(conn, identity_id, domain, phase)


def _complete_phase(
    conn: sqlite3.Connection, identity_id: str, domain: str, phase: int
) -> None:
    conn.execute(
        "UPDATE warming_schedule SET completed_at = ? "
        "WHERE identity_id = ? AND target_domain = ? AND phase = ? AND completed_at IS NULL",
        (int(time.time()), identity_id, domain, phase),
    )


def is_phase_complete(
    conn: sqlite3.Connection, identity_id: str, domain: str, phase: int
) -> bool:
    row = _phase_row(conn, identity_id, domain, phase)
    return row is not None and row["completed_at"] is not None


def is_warming_complete(conn: sqlite3.Connection, identity_id: str, domain: str) -> bool:
    """True once FASE 2 (portal familiarization) is completed for this domain."""
    return is_phase_complete(conn, identity_id, domain, PHASE_PORTAL)


# ── Phase orchestration (real Camoufox — integration only) ────────────────────

async def run_phase1(identity: Identity, conn: sqlite3.Connection) -> None:
    """
    48h ambient warming. Uses Camoufox with identity proxy.
    Writes progress to warming_schedule table.

    One call performs a single ambient browsing session (visit ambient sites with
    organic dwell/scroll, no portals) and advances requests_done. The scheduler
    repeats across the window until the phase completes.
    """
    _ensure_phase_row(conn, identity.id, _AMBIENT_DOMAIN, PHASE_AMBIENT, _PHASE1_TARGET)
    if is_phase_complete(conn, identity.id, _AMBIENT_DOMAIN, PHASE_AMBIENT):
        return
    sites = _AMBIENT_SITES.get(identity.country)
    if not sites:
        raise ValueError(f"no ambient sites configured for country={identity.country!r}")

    from camoufox.async_api import AsyncCamoufox

    proxy = proxy_dict_from_url(identity.proxy_ip)
    async with AsyncCamoufox(headless=True, geoip=proxy is not None, proxy=proxy) as browser:
        page = await browser.new_page()
        for url in sites:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await behavioral.simulate_reading(page, (8, 25))
            except Exception as exc:
                log.debug("phase1 %s nav error %s: %s", identity.id, url, exc)
                continue
            _record_progress(conn, identity.id, _AMBIENT_DOMAIN, PHASE_AMBIENT)


async def run_phase2(identity: Identity, domain: str, conn: sqlite3.Connection) -> None:
    """
    24h portal familiarization. Uses Camoufox + Intent Engine.
    Persists storage_state + first _abck after completion.

    Visits the portal homepage with a persona-driven organic flow (NO extraction),
    then persists the resulting storageState and the first _abck token so later
    sessions can refresh without a full browser.
    """
    _ensure_phase_row(conn, identity.id, domain, PHASE_PORTAL, _PHASE2_TARGET)
    if is_phase_complete(conn, identity.id, domain, PHASE_PORTAL):
        return

    from camoufox.async_api import AsyncCamoufox

    persona = intent.pick_persona(identity.country)
    proxy = proxy_dict_from_url(identity.proxy_ip)
    home = f"https://{domain}/"
    async with AsyncCamoufox(headless=True, geoip=proxy is not None, proxy=proxy) as browser:
        page = await browser.new_page()
        try:
            await page.goto(home, wait_until="domcontentloaded", timeout=30_000)
            await behavioral.simulate_reading(page, persona.results_dwell_s)
            _record_progress(conn, identity.id, domain, PHASE_PORTAL)
            state = await browser.storage_state() if hasattr(browser, "storage_state") else await page.context.storage_state()
        except Exception as exc:
            log.warning("phase2 %s/%s aborted: %s", identity.id, domain, exc)
            return

    save_state(conn, identity.id, domain, state)
    token = extract_abck(state, domain)
    if token:
        from scrapers.engine.antidetect import sensor
        sensor.store_token(conn, identity.id, domain, token, int(time.time()) + _ABCK_TTL_S)
        log.info("phase2 %s/%s: first _abck persisted", identity.id, domain)


def enforce_no_extraction_before_warming(identity: Identity, domain: str) -> None:
    """Raise RuntimeError if extraction is attempted before warming_done=True."""
    if not identity.warming_done:
        raise RuntimeError(
            f"Identity {identity.id} attempted extraction on {domain} before warming. "
            "Retiring immediately. Do not use this identity again."
        )
