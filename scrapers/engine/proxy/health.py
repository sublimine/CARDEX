"""
Proxy health monitor — ban detector y quarantine automático.

Thresholds (SCRAPING_ENGINE.md §A2):
  success_rate < 0.7  → soft_degraded (no asignar a identidades premium)
  success_rate < 0.5  → quarantine_24h (no asignar a nadie)
  ban_count_24h >= 3  → quarantine_24h inmediato

Reintegración: tras 24h de quarantine → probar con request de diagnóstico.
  Éxito → active. Fallo → quarantine 48h más.
"""
from __future__ import annotations

import sqlite3
import time


def record_result(
    conn: sqlite3.Connection,
    proxy_ip: str,
    success: bool,
) -> None:
    """Update proxy success_rate rolling average. Trigger quarantine if thresholds hit."""
    raise NotImplementedError


def is_usable(conn: sqlite3.Connection, proxy_ip: str, require_premium: bool = False) -> bool:
    """
    Returns False if proxy is in quarantine or soft_degraded when premium required.
    """
    raise NotImplementedError


async def probe(proxy_ip: str, proxy_url: str) -> bool:
    """
    Send a benign request through the proxy to verify it's alive.
    Used to release proxies from quarantine after 24h.
    """
    raise NotImplementedError
