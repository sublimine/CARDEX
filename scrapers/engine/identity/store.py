"""
Identity store — SQLite CRUD para identidades como activos financieros.

Todas las escrituras son INSERT o UPDATE atómicos.
Nunca se borran identidades — se retiran (retired_at + retire_reason).
El historial completo de cada identidad persiste en engine.db.
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from scrapers.engine.identity.profile import Identity, IdentityStatus


def save(conn: sqlite3.Connection, identity: Identity) -> None:
    """INSERT or UPDATE identity. Upsert by id."""
    raise NotImplementedError


def get(conn: sqlite3.Connection, identity_id: str) -> Identity | None:
    raise NotImplementedError


def pick_for_portal(
    conn: sqlite3.Connection,
    country: str,
    domain: str,
    min_trust: float = 0.0,
    require_warming: bool = True,
) -> Identity | None:
    """
    Select best available identity for (country, domain).
    Priority: trust_score DESC, last_used ASC (prefer rested identities).
    Respects proxy affinity: prefers identity that last used this domain.
    Returns None if no eligible identity available (triggers warming start).
    """
    raise NotImplementedError


def update_trust(
    conn: sqlite3.Connection,
    identity_id: str,
    delta: float,
    retire_if_below: float = -5.0,
) -> None:
    """
    Apply trust_score delta. Transitions:
      trust_score < 0  → quarantine (48h)
      trust_score < -5 → retired (permanent)
    See SCRAPING_ENGINE.md §A1 invariant 4.
    """
    raise NotImplementedError


def list_by_status(
    conn: sqlite3.Connection,
    status: IdentityStatus,
    country: str | None = None,
) -> Sequence[Identity]:
    raise NotImplementedError


def premium_count(conn: sqlite3.Connection, country: str | None = None) -> int:
    """Count identities with trust_score >= 7.0 and status=active."""
    raise NotImplementedError
