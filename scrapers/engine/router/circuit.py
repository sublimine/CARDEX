"""
Circuit breaker por (domain, tier).

Estados: CLOSED → OPEN → HALF_OPEN → CLOSED|OPEN
  CLOSED:     operación normal
  OPEN:       3 fallos en 60s → open 120s. Escalate al siguiente tier.
  HALF_OPEN:  tras 120s → 1 probe request. Éxito → CLOSED. Fallo → OPEN otra vez.

Persistencia: engine.db tabla domain_tier_state.
Métricas: circuit_breaker_state{domain, tier} → Prometheus.

The OPEN→HALF_OPEN transition is *time-based* and computed on read (get_state is
side-effect free): a row stored OPEN whose opened_at is older than _OPEN_DURATION_S
is logically HALF_OPEN. record_success / record_failure persist the resulting state.
"""
from __future__ import annotations

import sqlite3
import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_FAIL_THRESHOLD = 3
_FAIL_WINDOW_S = 60
_OPEN_DURATION_S = 120
_EWMA_ALPHA = 0.1  # success_rate smoothing factor


def _ensure_row(conn: sqlite3.Connection, domain: str, tier: str) -> None:
    conn.execute(
        "INSERT INTO domain_tier_state (domain, tier) VALUES (?, ?) "
        "ON CONFLICT(domain, tier) DO NOTHING",
        (domain, tier),
    )


def _load(conn: sqlite3.Connection, domain: str, tier: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM domain_tier_state WHERE domain = ? AND tier = ?",
        (domain, tier),
    ).fetchone()


def _logical_state(row: sqlite3.Row | None, now: int) -> CircuitState:
    """Stored state with the time-based OPEN→HALF_OPEN transition applied."""
    if row is None:
        return CircuitState.CLOSED
    stored = CircuitState(row["circuit_state"])
    if stored is CircuitState.OPEN:
        opened_at = row["opened_at"] or 0
        if now - opened_at >= _OPEN_DURATION_S:
            return CircuitState.HALF_OPEN
    return stored


def get_state(conn: sqlite3.Connection, domain: str, tier: str) -> CircuitState:
    """Read-only current logical state. Never writes."""
    return _logical_state(_load(conn, domain, tier), int(time.time()))


def record_failure(
    conn: sqlite3.Connection, domain: str, tier: str, now: int | None = None
) -> CircuitState:
    """Record a failure and return the new persisted state."""
    ts = int(time.time()) if now is None else now
    _ensure_row(conn, domain, tier)
    row = _load(conn, domain, tier)
    logical = _logical_state(row, ts)

    if logical is CircuitState.HALF_OPEN:
        # A failed probe re-opens immediately for another full duration.
        new_state, fail_count, opened_at = CircuitState.OPEN, _FAIL_THRESHOLD, ts
    elif logical is CircuitState.OPEN:
        new_state, fail_count, opened_at = CircuitState.OPEN, row["fail_count"], row["opened_at"]
    else:  # CLOSED — apply rolling-window counting
        last_fail = row["last_fail"] or 0
        within_window = (ts - last_fail) <= _FAIL_WINDOW_S
        fail_count = (row["fail_count"] + 1) if within_window else 1
        if fail_count >= _FAIL_THRESHOLD:
            new_state, opened_at = CircuitState.OPEN, ts
        else:
            new_state, opened_at = CircuitState.CLOSED, None

    success_rate = (1 - _EWMA_ALPHA) * row["success_rate"]  # failure sample = 0.0
    conn.execute(
        "UPDATE domain_tier_state SET circuit_state=?, fail_count=?, opened_at=?, "
        "success_rate=?, last_fail=? WHERE domain=? AND tier=?",
        (new_state.value, fail_count, opened_at, success_rate, ts, domain, tier),
    )
    return new_state


def record_success(
    conn: sqlite3.Connection, domain: str, tier: str, now: int | None = None
) -> CircuitState:
    """Record a success and return the new persisted state."""
    ts = int(time.time()) if now is None else now
    _ensure_row(conn, domain, tier)
    row = _load(conn, domain, tier)
    logical = _logical_state(row, ts)

    if logical is CircuitState.OPEN:
        # Still inside the open window — a stray success does not close the breaker.
        new_state, fail_count, opened_at = CircuitState.OPEN, row["fail_count"], row["opened_at"]
    else:  # CLOSED or HALF_OPEN probe success → (re)close cleanly
        new_state, fail_count, opened_at = CircuitState.CLOSED, 0, None

    success_rate = (1 - _EWMA_ALPHA) * row["success_rate"] + _EWMA_ALPHA  # sample = 1.0
    conn.execute(
        "UPDATE domain_tier_state SET circuit_state=?, fail_count=?, opened_at=?, "
        "success_rate=?, last_success=? WHERE domain=? AND tier=?",
        (new_state.value, fail_count, opened_at, success_rate, ts, domain, tier),
    )
    return new_state


def force_open(
    conn: sqlite3.Connection, domain: str, tier: str, now: int | None = None
) -> None:
    """
    Force the breaker OPEN immediately, bypassing the rolling-window count.

    Used by the escalator as the definitive "this tier is burned, move up"
    trigger so the persisted state and the live recomputation agree: a single
    record_failure would only bump fail_count and leave the breaker CLOSED.
    Idempotent on an already-open breaker (resets the open window to `now`).
    """
    ts = int(time.time()) if now is None else now
    _ensure_row(conn, domain, tier)
    conn.execute(
        "UPDATE domain_tier_state SET circuit_state=?, fail_count=?, opened_at=?, "
        "last_fail=? WHERE domain=? AND tier=?",
        (CircuitState.OPEN.value, _FAIL_THRESHOLD, ts, ts, domain, tier),
    )


def is_open(conn: sqlite3.Connection, domain: str, tier: str) -> bool:
    return get_state(conn, domain, tier) == CircuitState.OPEN
