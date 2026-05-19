"""
Proxy pool manager — asignación y salud de proxies por tier y país.

Tres pools con propósito exclusivo (nunca mezclados):
  ISP_STICKY:           Decodo — AS24, kleinanzeigen, coches.net
  RESIDENTIAL_ROTATING: Oxylabs — leboncoin, lacentrale (DataDome)
  MOBILE:               Decodo Mobile — fallback ASN datacenter bloqueado

Invariantes:
  - Un proxy se asigna a una identidad en creación y no cambia.
  - La afinidad proxy↔dominio se mantiene durante toda la sesión.
  - Proxies en quarantine nunca asignados a identidades premium.
  - La rotación RESIDENTIAL es por sesión, NO por request (JA3 invariant §22).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum

from scrapers.engine.identity.profile import ProxyTier


@dataclass
class Proxy:
    ip: str
    port: int
    username: str
    password: str
    tier: ProxyTier
    provider: str          # decodo|oxylabs|bright_data
    country: str
    success_rate: float = 1.0
    ban_count_24h: int = 0
    status: str = "active"  # active|soft_degraded|quarantine_24h

    @property
    def url(self) -> str:
        return f"http://{self.username}:{self.password}@{self.ip}:{self.port}"

    @property
    def playwright_dict(self) -> dict:
        return {"server": f"http://{self.ip}:{self.port}", "username": self.username, "password": self.password}


def pick(
    conn: sqlite3.Connection,
    tier: ProxyTier,
    country: str,
    domain: str,
    require_not_quarantine: bool = True,
) -> Proxy | None:
    """
    Pick best proxy for (tier, country, domain).
    Respects domain affinity: same proxy for same domain per session.
    Returns None if no eligible proxy available → trigger MOBILE fallback.
    """
    raise NotImplementedError


def record_success(conn: sqlite3.Connection, proxy_ip: str) -> None:
    raise NotImplementedError


def record_ban(conn: sqlite3.Connection, proxy_ip: str) -> None:
    """Increment ban_count_24h. If >= 3 bans in 24h → quarantine_24h."""
    raise NotImplementedError


def health_summary(conn: sqlite3.Connection) -> dict:
    """Return success_rate by tier and count of available proxies per tier."""
    raise NotImplementedError
