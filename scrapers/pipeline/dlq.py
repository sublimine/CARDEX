"""
Dead-letter queue — classify a failure and persist its recovery schedule.

SCRAPING_ENGINE.md §C4 maps each failure reason to a recovery action:

    fetch_error      retry with a fresh identity in 1h
    parse_error      no auto-retry — escalate to a human for schema validation
    poison_detected  discard permanently
    soft_block       retry with a *premium* identity in 24h
    rate_limited     retry per the server's Retry-After header

`recovery_for` is the pure policy function (reason → RecoveryAction); the rest are
thin writers over the `dlq` table. A repeat failure for the same URL UPSERTs,
incrementing `fail_count` and refreshing the schedule rather than duplicating the
row. `retry_after` is NULL for terminal/human reasons, which is exactly what keeps
them out of `due_items` — non-retryable work never re-enters the loop on its own.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import Enum

from scrapers.pipeline.delta import url_hash

# Default backoffs (seconds) per §C4.
_FETCH_RETRY_S = 3_600       # 1h
_SOFT_BLOCK_RETRY_S = 86_400  # 24h
_RATE_LIMIT_DEFAULT_S = 60   # fallback when Retry-After is missing/unparseable


class DlqReason(str, Enum):
    """Why a URL landed in the DLQ; the stored `dlq_reason` value."""

    FETCH_ERROR = "fetch_error"
    PARSE_ERROR = "parse_error"
    POISON_DETECTED = "poison_detected"
    SOFT_BLOCK = "soft_block"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class RecoveryAction:
    """How to recover a failed URL. Only `retryable` items get a `retry_after`."""

    retryable: bool
    delay_s: int | None = None
    needs_human: bool = False
    premium_required: bool = False
    terminal: bool = False


def _retry_after_seconds(header: str | None, now_ts: int) -> int:
    """Parse a Retry-After header (delta-seconds or HTTP-date) → seconds from now."""
    if not header:
        return _RATE_LIMIT_DEFAULT_S
    raw = header.strip()
    if raw.isdigit():
        return int(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return _RATE_LIMIT_DEFAULT_S
    delta = int(when.timestamp()) - now_ts
    return delta if delta > 0 else _RATE_LIMIT_DEFAULT_S


def recovery_for(
    reason: DlqReason,
    *,
    retry_after_header: str | None = None,
    now: int | None = None,
) -> RecoveryAction:
    """Map a §C4 reason to its recovery action (pure policy, no DB)."""
    if reason is DlqReason.FETCH_ERROR:
        return RecoveryAction(retryable=True, delay_s=_FETCH_RETRY_S)
    if reason is DlqReason.SOFT_BLOCK:
        return RecoveryAction(retryable=True, delay_s=_SOFT_BLOCK_RETRY_S, premium_required=True)
    if reason is DlqReason.RATE_LIMITED:
        ts = int(time.time()) if now is None else now
        return RecoveryAction(retryable=True, delay_s=_retry_after_seconds(retry_after_header, ts))
    if reason is DlqReason.PARSE_ERROR:
        return RecoveryAction(retryable=False, needs_human=True)
    return RecoveryAction(retryable=False, terminal=True)  # POISON_DETECTED


def record_failure(
    conn: sqlite3.Connection,
    *,
    url: str,
    portal: str,
    reason: DlqReason,
    error: str | None = None,
    now: int | None = None,
    retry_after_header: str | None = None,
) -> RecoveryAction:
    """
    UPSERT a failure into the DLQ and return its recovery action.

    First failure inserts the row; a repeat for the same URL increments fail_count
    and refreshes last_fail/last_error/dlq_reason/retry_after. `retry_after` is the
    next-eligible epoch for retryable reasons, NULL otherwise.
    """
    ts = int(time.time()) if now is None else now
    action = recovery_for(reason, retry_after_header=retry_after_header, now=ts)
    retry_after = ts + action.delay_s if (action.retryable and action.delay_s is not None) else None
    h = url_hash(url)

    conn.execute(
        "INSERT INTO dlq "
        "(url_hash, url, portal, fail_count, dlq_reason, last_error, first_fail, last_fail, retry_after) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?) "
        "ON CONFLICT(url_hash) DO UPDATE SET "
        "  fail_count = fail_count + 1, "
        "  dlq_reason = excluded.dlq_reason, "
        "  last_error = excluded.last_error, "
        "  last_fail  = excluded.last_fail, "
        "  retry_after = excluded.retry_after",
        (h, url, portal, reason.value, error, ts, ts, retry_after),
    )
    return action


def due_items(conn: sqlite3.Connection, now: int | None = None) -> list[sqlite3.Row]:
    """Retryable rows whose `retry_after` has arrived, soonest first (NULL excluded)."""
    ts = int(time.time()) if now is None else now
    return conn.execute(
        "SELECT * FROM dlq WHERE retry_after IS NOT NULL AND retry_after <= ? "
        "ORDER BY retry_after ASC",
        (ts,),
    ).fetchall()


def size(conn: sqlite3.Connection) -> int:
    """Total rows currently in the DLQ (drives the dlq-size gauge)."""
    return conn.execute("SELECT COUNT(*) FROM dlq").fetchone()[0]


def resolve(conn: sqlite3.Connection, url_hash_value: str) -> None:
    """Remove a URL from the DLQ once it has been successfully recovered."""
    conn.execute("DELETE FROM dlq WHERE url_hash = ?", (url_hash_value,))
