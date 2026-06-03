"""
Identity store — SQLite CRUD para identidades como activos financieros.

Todas las escrituras son INSERT o UPDATE atómicos (upsert by id). Nunca se borran
identidades — se retiran (retired_at + retire_reason). El historial completo de
cada identidad persiste en engine.db.
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from typing import Sequence

from scrapers.engine.identity.profile import (
    BrowserFingerprint,
    Identity,
    IdentityStatus,
    ProxyTier,
    TCPProfile,
    TLSProfile,
)

# trust_score thresholds — SCRAPING_ENGINE.md §A1 invariant 4.
_QUARANTINE_BELOW = 0.0
_RETIRE_BELOW = -5.0
_QUARANTINE_SECONDS = 48 * 3600
_PREMIUM_TRUST = 7.0


def _serialize_fp(fp: BrowserFingerprint | None) -> str:
    return json.dumps(dataclasses.asdict(fp)) if fp is not None else "null"


def _deserialize_fp(raw: str | None) -> BrowserFingerprint | None:
    if not raw or raw == "null":
        return None
    return BrowserFingerprint(**json.loads(raw))


def _row_to_identity(row: sqlite3.Row) -> Identity:
    return Identity(
        id=row["id"],
        country=row["country"],
        proxy_ip=row["proxy_ip"],
        proxy_tier=ProxyTier(row["proxy_tier"]),
        proxy_provider=row["proxy_provider"],
        tcp_profile=TCPProfile(row["tcp_profile"]),
        tls_profile=TLSProfile(row["tls_profile"]),
        fingerprint=_deserialize_fp(row["fingerprint"]),
        storage_state=row["storage_state"],
        abck_tokens=json.loads(row["abck_tokens"] or "{}"),
        browsing_history=json.loads(row["browsing_history"] or "[]"),
        status=IdentityStatus(row["status"]),
        trust_score=row["trust_score"],
        request_count=row["request_count"],
        ban_count=row["ban_count"],
        warming_done=bool(row["warming_done"]),
        created_at=row["created_at"],
        last_used=row["last_used"],
        quarantine_until=row["quarantine_until"],
        retired_at=row["retired_at"],
        retire_reason=row["retire_reason"],
    )


def save(conn: sqlite3.Connection, identity: Identity) -> None:
    """INSERT or UPDATE identity. Upsert by id."""
    conn.execute(
        """
        INSERT INTO identities (
            id, country, status, proxy_ip, proxy_tier, proxy_provider,
            tcp_profile, tls_profile, fingerprint, storage_state, abck_tokens,
            browsing_history, trust_score, request_count, ban_count,
            warming_done, quarantine_until, created_at, last_used,
            retired_at, retire_reason
        ) VALUES (
            :id, :country, :status, :proxy_ip, :proxy_tier, :proxy_provider,
            :tcp_profile, :tls_profile, :fingerprint, :storage_state, :abck_tokens,
            :browsing_history, :trust_score, :request_count, :ban_count,
            :warming_done, :quarantine_until, :created_at, :last_used,
            :retired_at, :retire_reason
        )
        ON CONFLICT(id) DO UPDATE SET
            country=excluded.country,
            status=excluded.status,
            proxy_ip=excluded.proxy_ip,
            proxy_tier=excluded.proxy_tier,
            proxy_provider=excluded.proxy_provider,
            tcp_profile=excluded.tcp_profile,
            tls_profile=excluded.tls_profile,
            fingerprint=excluded.fingerprint,
            storage_state=excluded.storage_state,
            abck_tokens=excluded.abck_tokens,
            browsing_history=excluded.browsing_history,
            trust_score=excluded.trust_score,
            request_count=excluded.request_count,
            ban_count=excluded.ban_count,
            warming_done=excluded.warming_done,
            quarantine_until=excluded.quarantine_until,
            last_used=excluded.last_used,
            retired_at=excluded.retired_at,
            retire_reason=excluded.retire_reason
        """,
        {
            "id": identity.id,
            "country": identity.country,
            "status": identity.status.value,
            "proxy_ip": identity.proxy_ip,
            "proxy_tier": identity.proxy_tier.value,
            "proxy_provider": identity.proxy_provider,
            "tcp_profile": identity.tcp_profile.value,
            "tls_profile": identity.tls_profile.value,
            "fingerprint": _serialize_fp(identity.fingerprint),
            "storage_state": identity.storage_state,
            "abck_tokens": json.dumps(identity.abck_tokens),
            "browsing_history": json.dumps(identity.browsing_history),
            "trust_score": identity.trust_score,
            "request_count": identity.request_count,
            "ban_count": identity.ban_count,
            "warming_done": int(identity.warming_done),
            "quarantine_until": identity.quarantine_until,
            "created_at": identity.created_at,
            "last_used": identity.last_used,
            "retired_at": identity.retired_at,
            "retire_reason": identity.retire_reason,
        },
    )


def get(conn: sqlite3.Connection, identity_id: str) -> Identity | None:
    row = conn.execute(
        "SELECT * FROM identities WHERE id = ?", (identity_id,)
    ).fetchone()
    return _row_to_identity(row) if row is not None else None


def pick_for_portal(
    conn: sqlite3.Connection,
    country: str,
    domain: str,
    min_trust: float = 0.0,
    require_warming: bool = True,
) -> Identity | None:
    """
    Select best available identity for (country, domain).

    Priority: identities that already hold a session for this domain (proxy
    affinity / warm _abck) first, then trust_score DESC, then last_used ASC so
    rested identities are preferred over recently hammered ones.
    Returns None if no eligible identity exists (caller should start warming).
    """
    warming_clause = "AND warming_done = 1" if require_warming else ""
    rows = conn.execute(
        f"""
        SELECT *,
               (CASE WHEN json_extract(abck_tokens, '$."' || ? || '"') IS NOT NULL
                     THEN 1 ELSE 0 END) AS has_affinity
        FROM identities
        WHERE country = ?
          AND status = 'active'
          AND trust_score >= ?
          {warming_clause}
          AND (quarantine_until IS NULL OR quarantine_until <= ?)
        ORDER BY has_affinity DESC,
                 trust_score DESC,
                 COALESCE(last_used, 0) ASC
        LIMIT 1
        """,
        (domain, country, min_trust, int(time.time())),
    ).fetchone()
    return _row_to_identity(rows) if rows is not None else None


def update_trust(
    conn: sqlite3.Connection,
    identity_id: str,
    delta: float,
    retire_if_below: float = _RETIRE_BELOW,
) -> None:
    """
    Apply trust_score delta atomically and transition status:
      trust_score < retire_if_below → retired (permanent)
      trust_score < 0               → quarantine (48h)
    See SCRAPING_ENGINE.md §A1 invariant 4.
    """
    row = conn.execute(
        "SELECT trust_score, status FROM identities WHERE id = ?", (identity_id,)
    ).fetchone()
    if row is None:
        return
    if row["status"] == IdentityStatus.RETIRED.value:
        return  # retired is terminal

    new_score = row["trust_score"] + delta
    now = int(time.time())

    if new_score < retire_if_below:
        conn.execute(
            "UPDATE identities SET trust_score=?, status=?, retired_at=?, "
            "retire_reason=? WHERE id=?",
            (new_score, IdentityStatus.RETIRED.value, now, "trust_collapsed", identity_id),
        )
    elif new_score < _QUARANTINE_BELOW:
        conn.execute(
            "UPDATE identities SET trust_score=?, status=?, quarantine_until=? "
            "WHERE id=?",
            (
                new_score,
                IdentityStatus.QUARANTINE.value,
                now + _QUARANTINE_SECONDS,
                identity_id,
            ),
        )
    else:
        conn.execute(
            "UPDATE identities SET trust_score=? WHERE id=?", (new_score, identity_id)
        )


def list_by_status(
    conn: sqlite3.Connection,
    status: IdentityStatus,
    country: str | None = None,
) -> Sequence[Identity]:
    if country is None:
        rows = conn.execute(
            "SELECT * FROM identities WHERE status = ?", (status.value,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM identities WHERE status = ? AND country = ?",
            (status.value, country),
        ).fetchall()
    return [_row_to_identity(r) for r in rows]


def premium_count(conn: sqlite3.Connection, country: str | None = None) -> int:
    """Count identities with trust_score >= 7.0 and status=active."""
    if country is None:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM identities WHERE status='active' AND trust_score >= ?",
            (_PREMIUM_TRUST,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM identities WHERE status='active' "
            "AND trust_score >= ? AND country = ?",
            (_PREMIUM_TRUST, country),
        ).fetchone()
    return int(row["n"])
