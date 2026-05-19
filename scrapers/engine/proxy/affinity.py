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

from scrapers.engine.proxy.pool import Proxy


def get_affine_proxy(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
) -> Proxy | None:
    """Return the proxy previously assigned to (identity, domain), if still active."""
    raise NotImplementedError


def set_affine_proxy(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
    proxy: Proxy,
) -> None:
    """Persist proxy affinity for (identity, domain)."""
    raise NotImplementedError
