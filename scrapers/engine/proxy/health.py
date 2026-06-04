"""
Proxy health monitor — ban detector y quarantine automático.

Thresholds (SCRAPING_ENGINE.md §A2):
  success_rate < 0.7  → soft_degraded (no asignar a identidades premium)
  success_rate < 0.5  → quarantine_24h (no asignar a nadie)
  ban_count_24h >= 3  → quarantine_24h inmediato

Reintegración: tras 24h de quarantine → probar con request de diagnóstico.
  Éxito → active. Fallo → quarantine 48h más.

This module owns every write to a proxy_health row's health fields (success_rate,
ban_count_24h, status, quarantine_until). pool.py delegates record_success /
record_ban here so the threshold logic lives in exactly one place (_status_for).
The OPEN→eligible transition is time-based and computed on read (is_usable), like
the circuit breaker: a row whose quarantine_until has elapsed is logically
testable again even though the stored status still reads 'quarantine_24h'.
"""
from __future__ import annotations

import logging
import sqlite3
import time

log = logging.getLogger("proxy.health")

# Status values persisted in proxy_health.status.
STATUS_ACTIVE = "active"
STATUS_SOFT_DEGRADED = "soft_degraded"
STATUS_QUARANTINE = "quarantine_24h"

_EWMA_ALPHA = 0.2          # success_rate smoothing — heavier than the breaker's 0.1
_SOFT_DEGRADE_BELOW = 0.7
_QUARANTINE_BELOW = 0.5
_BAN_QUARANTINE_THRESHOLD = 3
_QUARANTINE_SECONDS = 24 * 3600

# Diagnostic probe — a benign IP-echo endpoint reachable through any live proxy.
_PROBE_URL = "https://api.ipify.org"
_PROBE_TIMEOUT_S = 15
_PROBE_IMPERSONATE = "chrome"


def _load(conn: sqlite3.Connection, proxy_ip: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM proxy_health WHERE proxy_ip = ?", (proxy_ip,)
    ).fetchone()


def _status_for(
    success_rate: float, ban_count_24h: int, now: int
) -> tuple[str, int | None]:
    """
    Pure threshold decision: (status, quarantine_until). No I/O, no row state.

    Ordered worst-first so a ban storm or a collapsed success_rate always wins
    over a merely-degraded reading.
    """
    if ban_count_24h >= _BAN_QUARANTINE_THRESHOLD or success_rate < _QUARANTINE_BELOW:
        return STATUS_QUARANTINE, now + _QUARANTINE_SECONDS
    if success_rate < _SOFT_DEGRADE_BELOW:
        return STATUS_SOFT_DEGRADED, None
    return STATUS_ACTIVE, None


def _quarantined(row: sqlite3.Row, now: int) -> bool:
    """True only while the 24h quarantine window is still in the future."""
    qu = row["quarantine_until"]
    return row["status"] == STATUS_QUARANTINE and qu is not None and now < qu


def record_result(
    conn: sqlite3.Connection, proxy_ip: str, success: bool
) -> None:
    """
    Update proxy success_rate (EWMA) and recompute status. Soft path: timeouts and
    non-ban failures. A row mid-quarantine keeps its status frozen until the window
    elapses, so a stray probe success cannot prematurely un-quarantine it.
    """
    now = int(time.time())
    row = _load(conn, proxy_ip)
    if row is None:
        return  # unknown proxy — pool.register owns row creation
    sample = 1.0 if success else 0.0
    new_rate = (1 - _EWMA_ALPHA) * row["success_rate"] + _EWMA_ALPHA * sample
    request_count = row["request_count"] + 1
    fail_count = row["fail_count"] + (0 if success else 1)

    if _quarantined(row, now):
        status, quarantine_until = STATUS_QUARANTINE, row["quarantine_until"]
    else:
        status, quarantine_until = _status_for(new_rate, row["ban_count_24h"], now)

    last_success_at = now if success else row["last_success_at"]
    conn.execute(
        "UPDATE proxy_health SET success_rate=?, request_count=?, fail_count=?, "
        "status=?, quarantine_until=?, last_success_at=? WHERE proxy_ip=?",
        (new_rate, request_count, fail_count, status, quarantine_until,
         last_success_at, proxy_ip),
    )


def record_ban(conn: sqlite3.Connection, proxy_ip: str) -> None:
    """
    Hard path: a confirmed block. Increment ban_count_24h, count it as a failure
    sample, and re-evaluate status — the 3rd ban in the window forces quarantine.
    Unlike record_result this never freezes status: a ban must be able to escalate
    an already-degraded proxy straight into quarantine.
    """
    now = int(time.time())
    row = _load(conn, proxy_ip)
    if row is None:
        return
    ban_count = row["ban_count_24h"] + 1
    new_rate = (1 - _EWMA_ALPHA) * row["success_rate"]  # ban = failure sample 0.0
    request_count = row["request_count"] + 1
    fail_count = row["fail_count"] + 1
    status, quarantine_until = _status_for(new_rate, ban_count, now)
    conn.execute(
        "UPDATE proxy_health SET success_rate=?, request_count=?, fail_count=?, "
        "ban_count_24h=?, status=?, quarantine_until=?, last_ban_at=? "
        "WHERE proxy_ip=?",
        (new_rate, request_count, fail_count, ban_count, status, quarantine_until,
         now, proxy_ip),
    )


def is_usable(
    conn: sqlite3.Connection, proxy_ip: str, require_premium: bool = False
) -> bool:
    """
    Eligibility for assignment right now.

    False while quarantine_until is in the future. Once the window elapses the
    proxy is testable again (the next request IS the diagnostic probe). For a
    premium identity the bar is higher: the live threshold reading must be exactly
    'active' — a soft_degraded proxy is recomputed and rejected even if its stored
    status is stale.
    """
    now = int(time.time())
    row = _load(conn, proxy_ip)
    if row is None:
        return False
    if _quarantined(row, now):
        return False
    if require_premium:
        live_status, _ = _status_for(row["success_rate"], row["ban_count_24h"], now)
        if live_status != STATUS_ACTIVE:
            return False
    return True


async def probe(proxy_ip: str, proxy_url: str) -> bool:
    """
    Send a benign request through the proxy to verify it's alive. Used to release
    proxies from quarantine after 24h. A 200 from the IP-echo endpoint = alive.
    """
    # Lazy import keeps the pure threshold logic importable without curl_cffi.
    from curl_cffi.requests import AsyncSession

    proxies = {"https": proxy_url, "http": proxy_url}
    try:
        async with AsyncSession() as sess:
            r = await sess.get(
                _PROBE_URL,
                impersonate=_PROBE_IMPERSONATE,
                timeout=_PROBE_TIMEOUT_S,
                proxies=proxies,
            )
        return r.status_code == 200
    except Exception as exc:  # network/TLS failure — proxy is not alive
        log.warning("probe failed for %s: %s", proxy_ip, exc)
        return False
