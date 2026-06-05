"""
Direct-identity provisioning — no-proxy identities for T0/T1 portals.

T0/T1 portals (open JSON APIs, curl_cffi SSR) need no residential proxy: a
coherent, rotated User-Agent over a direct TLS-impersonated session is enough.
But the engine only scrapes a (country, domain) once an *active, warmed* identity
exists for it (coordinator.make_live_session → store.pick_for_portal). With no
proxy budget, nothing ever created such identities, so every T0/T1 job looped on
NO_IDENTITY forever. This module mints direct identities straight into engine.db
at bootstrap so the coordinator can serve T0/T1 immediately, without a proxy.

Direct identities are "born warmed": warming exists to build the cookie/_abck gate
that Akamai/DataDome (T2/T3 browsers) demand — an open JSON API has no such gate,
so there is nothing to warm against. They are persisted active, warming_done=1,
with a small positive trust baseline that clears pick_for_portal's min_trust=0.0
floor for T0/T1 while staying far below the 7.0 premium gate, so a direct identity
can never qualify for a T3 (DataDome) portal.

Idempotent: identity ids are derived deterministically from (country, index), so
re-running bootstrap converges on the same N identities per country instead of
growing the pool. Existing identities are left untouched — their trust lifecycle
is owned by the engine (aging.py) — only missing ones are created.
"""
from __future__ import annotations

import dataclasses
import sqlite3
import time
import uuid

from scrapers.engine.identity import store
from scrapers.engine.identity.profile import (
    COUNTRY_TIMEZONES,
    IdentityStatus,
    generate_direct,
)

# Fixed namespace so deterministic ids are stable across runs and never collide
# with the random uuid4 ids of proxied identities.
_DIRECT_NS = uuid.UUID("cade0000-0000-4000-8000-000000000000")

# How many direct identities to keep per country. One already unblocks a country;
# a small pool gives resilience — if one is soft-blocked into quarantine, the
# others keep that country scraping.
DEFAULT_PER_COUNTRY = 3

# Cleared by pick_for_portal's min_trust=0.0 for T0/T1; far under the 7.0 premium
# gate so a direct identity is structurally ineligible for T3 portals.
_TRUST_BASELINE = 1.0


def _direct_id(country: str, index: int) -> str:
    """Deterministic, stable identity id for the (country, index) direct slot."""
    return str(uuid.uuid5(_DIRECT_NS, f"direct:{country}:{index}"))


def ensure_direct_identities(
    conn: sqlite3.Connection,
    per_country: int = DEFAULT_PER_COUNTRY,
    countries: list[str] | None = None,
) -> int:
    """
    Ensure `per_country` active, warmed, direct identities exist for each country.

    Defaults to every supported country (COUNTRY_TIMEZONES). Returns the number of
    identities newly created (0 when all are already present). Safe to call on
    every bootstrap — it only fills gaps, never resets an existing identity.
    """
    targets = countries if countries is not None else list(COUNTRY_TIMEZONES)
    now = int(time.time())

    # Compute the missing identities first (pure reads), then write them in one
    # explicit transaction. db.connect uses autocommit (isolation_level=None), so
    # a plain `with conn` would NOT make the writes atomic — without BEGIN/COMMIT
    # a crash mid-loop could leave some countries provisioned and others empty,
    # stranding their T0/T1 jobs on NO_IDENTITY until the next bootstrap.
    pending = []
    for country in targets:
        for index in range(per_country):
            iid = _direct_id(country, index)
            if store.get(conn, iid) is not None:
                continue  # already provisioned — leave its lifecycle intact
            identity = dataclasses.replace(
                generate_direct(country, identity_id=iid),
                status=IdentityStatus.ACTIVE,
                warming_done=True,
                trust_score=_TRUST_BASELINE,
                created_at=now,
            )
            pending.append(identity)

    if not pending:
        return 0

    conn.execute("BEGIN")
    try:
        for identity in pending:
            store.save(conn, identity)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(pending)
