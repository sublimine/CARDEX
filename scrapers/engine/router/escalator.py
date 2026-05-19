"""
Tier escalator — T1 → T2 → T3 automático en fallo.

Lógica:
  1. Intentar request con tier asignado en DOMAIN_TIER_REGISTRY
  2. Si circuit breaker OPEN para (domain, tier) → escalar al siguiente tier
  3. Si request falla (soft-block / hard-block) → record_failure en circuit breaker
  4. Tras FAIL_THRESHOLD → circuit OPEN → próximo request usa tier+1
  5. El cambio de tier efectivo persiste en engine.db (domain_tier_state.effective_tier)
  6. Escalation event → log structured + Prometheus counter

Restricción: T3 requiere identidad premium (trust_score >= 7.0).
Si no hay identidad premium disponible → esperar (no degradar a T2 silenciosamente).
"""
from __future__ import annotations

import sqlite3

from scrapers.engine.router.domain_map import Tier, get


_TIER_ORDER = [Tier.T0, Tier.T1, Tier.T2, Tier.T3]


def next_tier(current: Tier) -> Tier | None:
    """Return next tier in escalation chain, or None if already at T3."""
    idx = _TIER_ORDER.index(current)
    return _TIER_ORDER[idx + 1] if idx < len(_TIER_ORDER) - 1 else None


def get_effective_tier(conn: sqlite3.Connection, domain: str) -> Tier:
    """Return the tier to use for domain right now, considering escalation history."""
    raise NotImplementedError


def escalate(conn: sqlite3.Connection, domain: str, from_tier: Tier) -> Tier | None:
    """
    Mark from_tier as failed for domain. Compute and persist new effective_tier.
    Returns new tier or None if T3 already (max escalation reached).
    """
    raise NotImplementedError
