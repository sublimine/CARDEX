"""
Circuit breaker por (domain, tier).

Estados: CLOSED → OPEN → HALF_OPEN → CLOSED|OPEN
  CLOSED:     operación normal
  OPEN:       3 fallos en 60s → open 120s. Escalate al siguiente tier.
  HALF_OPEN:  tras 120s → 1 probe request. Éxito → CLOSED. Fallo → OPEN otra vez.

Persistencia: engine.db tabla domain_tier_state.
Métricas: circuit_breaker_state{domain, tier} → Prometheus.
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


def get_state(conn: sqlite3.Connection, domain: str, tier: str) -> CircuitState:
    raise NotImplementedError


def record_failure(conn: sqlite3.Connection, domain: str, tier: str) -> CircuitState:
    """Record failure. Returns new state after applying threshold logic."""
    raise NotImplementedError


def record_success(conn: sqlite3.Connection, domain: str, tier: str) -> CircuitState:
    raise NotImplementedError


def is_open(conn: sqlite3.Connection, domain: str, tier: str) -> bool:
    return get_state(conn, domain, tier) == CircuitState.OPEN
