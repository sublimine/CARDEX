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

# trust_score deltas — SCRAPING_ENGINE.md §A1 invariant 4.
_SUCCESS_DELTA = 0.05
_SOFT_BLOCK_DELTA = -1.0
_HARD_BLOCK_DELTA = -3.0

# Quarantine re-evaluation thresholds.
_BAN_RETIRE_THRESHOLD = 3  # ban_count at/above which a quarantined id is burned
_REHAB_TRUST = 0.0         # neutral baseline given on release (a 'new' identity starts here)


def record_success(conn: sqlite3.Connection, identity_id: str) -> None:
    update_trust(conn, identity_id, _SUCCESS_DELTA)


def record_soft_block(conn: sqlite3.Connection, identity_id: str) -> None:
    update_trust(conn, identity_id, _SOFT_BLOCK_DELTA)


def record_hard_block(conn: sqlite3.Connection, identity_id: str) -> None:
    """Hard-block: trust penalty AND ban_count increment (the ban is the durable signal)."""
    conn.execute(
        "UPDATE identities SET ban_count = ban_count + 1 WHERE id = ?", (identity_id,)
    )
    update_trust(conn, identity_id, _HARD_BLOCK_DELTA)


def release_quarantine(conn: sqlite3.Connection, now: int | None = None) -> int:
    """
    Re-evaluate identities in quarantine whose quarantine_until has passed.

    Two disjoint outcomes (SCRAPING_ENGINE.md §A1 invariant 4):
      ban_count >= 3  → retired (permanent; the IP is burned across repeated bans)
      ban_count < 3   → active, trust reset to a neutral baseline (48h cool-off +
                        fresh proxy assignment on next pick is the second chance)

    Returns the count released back to active (retired ones are not 'released').
    """
    ts = int(time.time()) if now is None else now
    quarantine = IdentityStatus.QUARANTINE.value

    # Burned identities: hard-block cause. Permanent retirement.
    conn.execute(
        "UPDATE identities SET status=?, retired_at=?, retire_reason=?, "
        "quarantine_until=NULL "
        "WHERE status=? AND quarantine_until IS NOT NULL AND quarantine_until <= ? "
        "AND ban_count >= ?",
        (
            IdentityStatus.RETIRED.value,
            ts,
            "ban_threshold",
            quarantine,
            ts,
            _BAN_RETIRE_THRESHOLD,
        ),
    )

    # Survivors: soft-block cause. Released to active with a fresh trust baseline.
    cur = conn.execute(
        "UPDATE identities SET status=?, trust_score=?, quarantine_until=NULL "
        "WHERE status=? AND quarantine_until IS NOT NULL AND quarantine_until <= ? "
        "AND ban_count < ?",
        (
            IdentityStatus.ACTIVE.value,
            _REHAB_TRUST,
            quarantine,
            ts,
            _BAN_RETIRE_THRESHOLD,
        ),
    )
    return cur.rowcount


def is_premium(identity: Identity) -> bool:
    return identity.trust_score >= 7.0 and identity.status == IdentityStatus.ACTIVE
