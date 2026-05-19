"""
Identity aging — trust_score lifecycle y transiciones de estado.

Reglas (SCRAPING_ENGINE.md §A1 invariante 4):
  Request exitosa:   trust_score += 0.05
  Soft-block:        trust_score -= 1.0
  Hard-block:        trust_score -= 3.0, ban_count += 1
  trust_score < 0:   → quarantine 48h
  trust_score < -5:  → retired (permanente)
  trust_score >= 7:  → PREMIUM (elegible para T3 portales)

Identidades en quarantine se re-evalúan tras 48h:
  Si la causa fue soft-block con nueva IP disponible → active
  Si la causa fue hard-block (ban_count >= 3) → retired
"""
from __future__ import annotations

import sqlite3
import time

from scrapers.engine.identity.profile import Identity, IdentityStatus
from scrapers.engine.identity.store import update_trust


def record_success(conn: sqlite3.Connection, identity_id: str) -> None:
    update_trust(conn, identity_id, +0.05)


def record_soft_block(conn: sqlite3.Connection, identity_id: str) -> None:
    update_trust(conn, identity_id, -1.0)


def record_hard_block(conn: sqlite3.Connection, identity_id: str) -> None:
    update_trust(conn, identity_id, -3.0)


def release_quarantine(conn: sqlite3.Connection) -> int:
    """
    Re-evaluate identities in quarantine whose quarantine_until has passed.
    Returns count of identities released back to active.
    """
    raise NotImplementedError


def is_premium(identity: Identity) -> bool:
    return identity.trust_score >= 7.0 and identity.status == IdentityStatus.ACTIVE
