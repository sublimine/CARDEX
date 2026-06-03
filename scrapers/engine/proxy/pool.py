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

Responsibility split: this module owns selection (pick), registration (register)
and the fleet summary (health_summary). The per-proxy health state machine —
success_rate, bans, quarantine — lives in health.py; record_success / record_ban
here are thin delegators so the threshold logic stays single-sourced.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from scrapers.engine.identity.profile import ProxyTier
from scrapers.engine.proxy import health


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


def row_to_proxy(row: sqlite3.Row) -> Proxy:
    """Reconstruct a full Proxy (credentials included) from a proxy_health row."""
    return Proxy(
        ip=row["proxy_ip"],
        port=row["port"],
        username=row["username"],
        password=row["password"],
        tier=ProxyTier(row["tier"]),
        provider=row["provider"],
        country=row["country"],
        success_rate=row["success_rate"],
        ban_count_24h=row["ban_count_24h"],
        status=row["status"],
    )


def register(conn: sqlite3.Connection, proxy: Proxy) -> None:
    """
    Upsert a proxy into proxy_health (idempotent by proxy_ip).

    Identity and live health metrics are kept on re-registration: only the static
    connection fields (port/credentials/tier/provider/country) are refreshed, so
    re-seeding the fleet never resets a proxy's accumulated success_rate or bans.
    """
    conn.execute(
        "INSERT INTO proxy_health (proxy_ip, tier, provider, country, port, "
        "username, password) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(proxy_ip) DO UPDATE SET "
        "tier=excluded.tier, provider=excluded.provider, country=excluded.country, "
        "port=excluded.port, username=excluded.username, password=excluded.password",
        (proxy.ip, proxy.tier.value, proxy.provider, proxy.country,
         proxy.port, proxy.username, proxy.password),
    )


def pick(
    conn: sqlite3.Connection,
    tier: ProxyTier,
    country: str,
    domain: str,
    require_not_quarantine: bool = True,
) -> Proxy | None:
    """
    Pick best proxy for (tier, country, domain).

    This is the COLD-selection path. Per-session domain affinity is resolved by
    the caller via affinity.get_affine_proxy first; pick is what runs when no
    affine proxy exists yet (its result is then pinned by set_affine_proxy).
    `domain` is part of the contract for that reason but does not filter here.

    Ranking: healthiest first (success_rate DESC), then fewest recent bans, then
    most-recently-proven-alive. Quarantined proxies are excluded while their 24h
    window is open; once it elapses they are eligible again (diagnostic probe).
    Returns None when nothing qualifies → caller triggers MOBILE fallback.
    """
    del domain  # affinity is the caller's concern; see docstring
    now = int(time.time())
    params: list[object] = [tier.value, country]
    where = "tier = ? AND country = ?"
    if require_not_quarantine:
        where += (
            " AND (status != ? OR quarantine_until IS NULL OR quarantine_until <= ?)"
        )
        params += [health.STATUS_QUARANTINE, now]

    row = conn.execute(
        f"SELECT * FROM proxy_health WHERE {where} "
        "ORDER BY success_rate DESC, ban_count_24h ASC, "
        "COALESCE(last_success_at, 0) DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    return row_to_proxy(row) if row is not None else None


def record_success(conn: sqlite3.Connection, proxy_ip: str) -> None:
    health.record_result(conn, proxy_ip, True)


def record_ban(conn: sqlite3.Connection, proxy_ip: str) -> None:
    """Increment ban_count_24h. If >= 3 bans in 24h → quarantine_24h."""
    health.record_ban(conn, proxy_ip)


def health_summary(conn: sqlite3.Connection) -> dict:
    """Return success_rate by tier and count of available proxies per tier."""
    now = int(time.time())
    rows = conn.execute(
        "SELECT tier, "
        "AVG(success_rate) AS avg_rate, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status = ? AND quarantine_until IS NOT NULL "
        "         AND quarantine_until > ? THEN 0 ELSE 1 END) AS available "
        "FROM proxy_health GROUP BY tier",
        (health.STATUS_QUARANTINE, now),
    ).fetchall()
    return {
        r["tier"]: {
            "avg_success_rate": r["avg_rate"],
            "available": int(r["available"]),
            "total": int(r["total"]),
        }
        for r in rows
    }
