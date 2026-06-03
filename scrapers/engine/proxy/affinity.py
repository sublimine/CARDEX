"""
Proxy affinity — mismo proxy para el mismo dominio por toda la sesión.

Akamai y CF correlacionan requests de la misma sesión por IP.
Si la IP cambia mid-session → ban inmediato.
La afinidad se persiste en engine.db: identity_id + domain → proxy_ip.

Rotación RESIDENTIAL: nueva IP por SESIÓN, nunca por request.
Rotación ISP_STICKY:  misma IP por 4h (sticky session).
"""
from __future__ import annotations

import sqlite3
import time

from scrapers.engine.proxy import health
from scrapers.engine.proxy.pool import Proxy, row_to_proxy


def get_affine_proxy(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
) -> Proxy | None:
    """
    Return the proxy previously assigned to (identity, domain), if still active.

    Joins the affinity record to its live proxy_health row. A proxy whose 24h
    quarantine window is still open is treated as gone (returns None) so the
    caller falls back to a fresh pick rather than reusing a burned IP — but an
    expired window is allowed back through, consistent with health.is_usable.
    """
    row = conn.execute(
        "SELECT p.* FROM proxy_affinity a "
        "JOIN proxy_health p ON p.proxy_ip = a.proxy_ip "
        "WHERE a.identity_id = ? AND a.domain = ?",
        (identity_id, domain),
    ).fetchone()
    if row is None:
        return None
    now = int(time.time())
    qu = row["quarantine_until"]
    if row["status"] == health.STATUS_QUARANTINE and qu is not None and now < qu:
        return None
    return row_to_proxy(row)


def set_affine_proxy(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
    proxy: Proxy,
) -> None:
    """Persist proxy affinity for (identity, domain). Upsert — last pin wins."""
    conn.execute(
        "INSERT INTO proxy_affinity (identity_id, domain, proxy_ip, assigned_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(identity_id, domain) DO UPDATE SET "
        "proxy_ip=excluded.proxy_ip, assigned_at=excluded.assigned_at",
        (identity_id, domain, proxy.ip, int(time.time())),
    )
