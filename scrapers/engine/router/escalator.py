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
import time

from scrapers.engine.router import circuit, domain_map
from scrapers.engine.router.domain_map import Tier, get


_TIER_ORDER = [Tier.T0, Tier.T1, Tier.T2, Tier.T3]


def next_tier(current: Tier) -> Tier | None:
    """Return next tier in escalation chain, or None if already at T3."""
    idx = _TIER_ORDER.index(current)
    return _TIER_ORDER[idx + 1] if idx < len(_TIER_ORDER) - 1 else None


def _ceiling(domain: str, baseline: Tier) -> Tier:
    spec = get(domain)
    if spec is not None and spec.can_escalate_to is not None:
        return spec.can_escalate_to
    return baseline


def get_effective_tier(conn: sqlite3.Connection, domain: str) -> Tier:
    """
    Return the tier to use for domain right now.

    Recomputed from the live circuit-breaker snapshot (time-aware) so a tier whose
    breaker has recovered (half-open probe succeeded → closed) de-escalates back
    automatically. Single source of escalation logic lives in domain_map.effective_tier.
    """
    snapshot = {
        (domain, tier.value): circuit.get_state(conn, domain, tier.value).value
        for tier in _TIER_ORDER
    }
    return domain_map.effective_tier(domain, snapshot)


def escalate(conn: sqlite3.Connection, domain: str, from_tier: Tier) -> Tier | None:
    """
    Mark from_tier as failed for domain. Compute and persist new effective_tier.
    Returns new tier or None if the escalation ceiling is already reached.
    """
    spec = get(domain)
    baseline = spec.tier if spec is not None else from_tier
    ceiling = _ceiling(domain, baseline)

    nxt = next_tier(from_tier)
    if nxt is None or _TIER_ORDER.index(nxt) > _TIER_ORDER.index(ceiling):
        return None  # cannot escalate past the configured ceiling

    # Force the failing tier OPEN (idempotent) so the live recomputation in
    # get_effective_tier agrees with the effective_tier we cache below.
    now = int(time.time())
    circuit.force_open(conn, domain, from_tier.value, now)
    conn.execute(
        "INSERT INTO domain_tier_state (domain, tier, effective_tier, verified_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(domain, tier) DO UPDATE SET effective_tier=excluded.effective_tier",
        (domain, from_tier.value, nxt.value, now),
    )
    return nxt
