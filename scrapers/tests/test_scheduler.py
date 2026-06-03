"""
Scheduler tests — §C1 adaptive cadence + dispatch gates + plan loop.

Two layers, mirroring scheduler.py:

  * The pure decision functions (`decide_schedule`, `decide_dispatch`) are exercised
    with hand-picked numbers so every §C1 branch and clamp is pinned, with no DB.
  * The DB-touching layer (`enqueue`, `has_pending`, `plan_cycle`, `run`) is driven
    against the in-memory `conn` fixture plus an injected `due_source`/`sleep`, so the
    loop is tested without any live Postgres or wall clock (the prior system's fatal
    flaw was being testable only against live infra — directive #7).

Coroutines run synchronously with asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers import scheduler
from scrapers.engine.router import circuit
from scrapers.engine.router.domain_map import Tier
from scrapers.scheduler import (
    DispatchDecision,
    PortalChangeStats,
    ScheduleDecision,
    SchedulerConfig,
    decide_dispatch,
    decide_schedule,
    enqueue,
    has_pending,
    plan_cycle,
)

_NOW = 1_000_000
_HOUR = 3_600
_AS24_DE = "autoscout24.de"   # baseline T2 (escalates to T3) — no premium gate
_LEBONCOIN = "leboncoin.fr"   # baseline T3, no escalation — premium-gated


# --------------------------------------------------------------------------- #
# decide_schedule — §C1 adaptive cadence (pure)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_decide_schedule_change_halves_interval_and_pulls_next_forward() -> None:
    d = decide_schedule(10.0, changed=True, days_since_change=0, now=_NOW, min_h=1.0, max_h=720.0)
    assert d == ScheduleDecision(interval_h=5.0, next_scrape_at=_NOW + _HOUR)


@pytest.mark.unit
def test_decide_schedule_change_floors_interval_at_min() -> None:
    d = decide_schedule(1.0, changed=True, days_since_change=0, now=_NOW, min_h=1.0, max_h=720.0)
    assert d.interval_h == 1.0  # max(0.5, 1.0) — never below the floor
    assert d.next_scrape_at == _NOW + _HOUR


@pytest.mark.unit
def test_decide_schedule_static_grows_interval_by_half() -> None:
    d = decide_schedule(10.0, changed=False, days_since_change=7, now=_NOW, min_h=1.0, max_h=720.0)
    assert d.interval_h == 15.0
    assert d.next_scrape_at == _NOW + int(15.0 * _HOUR)


@pytest.mark.unit
def test_decide_schedule_static_caps_interval_at_max() -> None:
    d = decide_schedule(600.0, changed=False, days_since_change=30, now=_NOW, min_h=1.0, max_h=720.0)
    assert d.interval_h == 720.0  # min(900, 720) — capped at the 30-day ceiling


@pytest.mark.unit
def test_decide_schedule_stable_leaves_interval_untouched() -> None:
    # No change, but not yet static for 7 days → interval unchanged, next one out.
    d = decide_schedule(10.0, changed=False, days_since_change=3, now=_NOW, min_h=1.0, max_h=720.0)
    assert d.interval_h == 10.0
    assert d.next_scrape_at == _NOW + int(10.0 * _HOUR)


@pytest.mark.unit
def test_decide_schedule_boundary_six_days_is_still_stable() -> None:
    # 6 days < _STATIC_DAYS (7) → not yet relaxed.
    d = decide_schedule(8.0, changed=False, days_since_change=6, now=_NOW, min_h=1.0, max_h=720.0)
    assert d.interval_h == 8.0


# --------------------------------------------------------------------------- #
# decide_dispatch — dispatch gates (pure)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_decide_dispatch_open_circuit_blocks_every_tier() -> None:
    for tier in (Tier.T0, Tier.T1, Tier.T2, Tier.T3):
        d = decide_dispatch(tier, circuit_open=True, premium_count=99, min_premium=3)
        assert d == DispatchDecision(should_enqueue=False, reason="circuit_open")


@pytest.mark.unit
def test_decide_dispatch_t3_held_back_without_enough_premium() -> None:
    d = decide_dispatch(Tier.T3, circuit_open=False, premium_count=2, min_premium=3)
    assert d == DispatchDecision(should_enqueue=False, reason="insufficient_premium")


@pytest.mark.unit
def test_decide_dispatch_t3_allowed_once_premium_quota_met() -> None:
    d = decide_dispatch(Tier.T3, circuit_open=False, premium_count=3, min_premium=3)
    assert d == DispatchDecision(should_enqueue=True, reason="ok")


@pytest.mark.unit
def test_decide_dispatch_non_t3_ignores_premium_quota() -> None:
    # T2 enqueues even with zero premium identities — the gate is T3-only.
    d = decide_dispatch(Tier.T2, circuit_open=False, premium_count=0, min_premium=3)
    assert d == DispatchDecision(should_enqueue=True, reason="ok")


# --------------------------------------------------------------------------- #
# enqueue + has_pending — work_queue writers
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_enqueue_inserts_pending_row_and_returns_id(conn) -> None:
    job_id = enqueue(
        conn, portal=_AS24_DE, country="DE", tier=Tier.T2,
        scheduled_at=_NOW + 7200, priority=1, now=_NOW,
    )
    row = conn.execute("SELECT * FROM work_queue WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    assert row["portal"] == _AS24_DE
    assert row["country"] == "DE"
    assert row["tier"] == "T2"          # Tier.value persisted
    assert row["status"] == "pending"
    assert row["priority"] == 1
    assert row["attempts"] == 0
    assert row["created_at"] == _NOW
    assert row["scheduled_at"] == _NOW + 7200


@pytest.mark.unit
def test_has_pending_false_then_true_after_enqueue(conn) -> None:
    assert has_pending(conn, _AS24_DE, "DE") is False
    enqueue(conn, portal=_AS24_DE, country="DE", tier=Tier.T2, scheduled_at=_NOW, priority=5, now=_NOW)
    assert has_pending(conn, _AS24_DE, "DE") is True


@pytest.mark.unit
def test_has_pending_true_for_running_false_for_terminal(conn) -> None:
    job_id = enqueue(conn, portal=_AS24_DE, country="DE", tier=Tier.T2, scheduled_at=_NOW, priority=5, now=_NOW)
    conn.execute("UPDATE work_queue SET status='running' WHERE id=?", (job_id,))
    assert has_pending(conn, _AS24_DE, "DE") is True
    conn.execute("UPDATE work_queue SET status='done' WHERE id=?", (job_id,))
    assert has_pending(conn, _AS24_DE, "DE") is False


@pytest.mark.unit
def test_has_pending_scoped_to_portal_and_country(conn) -> None:
    enqueue(conn, portal=_AS24_DE, country="DE", tier=Tier.T2, scheduled_at=_NOW, priority=5, now=_NOW)
    assert has_pending(conn, _AS24_DE, "DE") is True
    assert has_pending(conn, "autoscout24.fr", "FR") is False


# --------------------------------------------------------------------------- #
# plan_cycle — dispatch gates + §C1 cadence + enqueue
# --------------------------------------------------------------------------- #
def _stats(portal: str, country: str, *, changed: bool, current_h: float = 10.0, days: int = 0) -> PortalChangeStats:
    return PortalChangeStats(
        portal=portal, country=country, current_interval_h=current_h,
        changed=changed, days_since_change=days,
    )


def _source(items: list[PortalChangeStats]):
    def due_source(_conn):
        return list(items)

    return due_source


@pytest.mark.unit
def test_plan_cycle_enqueues_changed_portal_with_priority(conn) -> None:
    ids = plan_cycle(conn, SchedulerConfig(), _source([_stats(_AS24_DE, "DE", changed=True)]), now=_NOW)

    assert len(ids) == 1
    row = conn.execute("SELECT * FROM work_queue WHERE id = ?", (ids[0],)).fetchone()
    assert row["portal"] == _AS24_DE
    assert row["tier"] == "T2"           # autoscout24.de effective tier
    assert row["priority"] == 1          # changed → jumps the queue
    assert row["scheduled_at"] == _NOW + _HOUR  # §C1: re-check in 1h


@pytest.mark.unit
def test_plan_cycle_enqueues_stable_portal_with_normal_priority(conn) -> None:
    ids = plan_cycle(
        conn, SchedulerConfig(),
        _source([_stats(_AS24_DE, "DE", changed=False, current_h=10.0, days=3)]),
        now=_NOW,
    )
    row = conn.execute("SELECT * FROM work_queue WHERE id = ?", (ids[0],)).fetchone()
    assert row["priority"] == 5
    assert row["scheduled_at"] == _NOW + int(10.0 * _HOUR)


@pytest.mark.unit
def test_plan_cycle_skips_when_circuit_open(conn) -> None:
    # autoscout24.de baseline T2 escalates to T3; open both so effective_tier (T3)
    # is itself OPEN → decide_dispatch blocks on circuit_open.
    circuit.force_open(conn, _AS24_DE, "T2")
    circuit.force_open(conn, _AS24_DE, "T3")

    ids = plan_cycle(conn, SchedulerConfig(), _source([_stats(_AS24_DE, "DE", changed=True)]), now=_NOW)

    assert ids == []
    assert conn.execute("SELECT COUNT(*) FROM work_queue").fetchone()[0] == 0


@pytest.mark.unit
def test_plan_cycle_skips_t3_without_premium(conn) -> None:
    # leboncoin.fr is a pure T3 portal; with zero premium FR identities the premium
    # gate holds it back rather than degrading to a weaker tier.
    ids = plan_cycle(conn, SchedulerConfig(), _source([_stats(_LEBONCOIN, "FR", changed=True)]), now=_NOW)

    assert ids == []
    assert conn.execute("SELECT COUNT(*) FROM work_queue").fetchone()[0] == 0


@pytest.mark.unit
def test_plan_cycle_skips_portal_with_work_already_queued(conn) -> None:
    enqueue(conn, portal=_AS24_DE, country="DE", tier=Tier.T2, scheduled_at=_NOW, priority=5, now=_NOW)

    ids = plan_cycle(conn, SchedulerConfig(), _source([_stats(_AS24_DE, "DE", changed=True)]), now=_NOW)

    assert ids == []
    # Still exactly the one pre-existing row — no duplicate piled on.
    assert conn.execute("SELECT COUNT(*) FROM work_queue").fetchone()[0] == 1


@pytest.mark.unit
def test_plan_cycle_processes_multiple_portals_independently(conn) -> None:
    items = [
        _stats(_AS24_DE, "DE", changed=True),
        _stats("autoscout24.fr", "FR", changed=False, days=10),
    ]
    ids = plan_cycle(conn, SchedulerConfig(), _source(items), now=_NOW)
    assert len(ids) == 2
    portals = {r["portal"] for r in conn.execute("SELECT portal FROM work_queue").fetchall()}
    assert portals == {_AS24_DE, "autoscout24.fr"}


# --------------------------------------------------------------------------- #
# run — bounded planning loop
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_plans_each_cycle_then_sleeps_bounded(conn) -> None:
    sleeps: list[float] = []

    async def sleep(d: float) -> None:
        sleeps.append(d)

    cfg = SchedulerConfig(poll_interval_s=30.0)
    asyncio.run(
        scheduler.run(
            cfg,
            due_source=_source([_stats(_AS24_DE, "DE", changed=True)]),
            conn=conn,
            sleep=sleep,
            now_fn=lambda: _NOW,
            max_cycles=1,
        )
    )

    rows = conn.execute("SELECT * FROM work_queue WHERE portal = ?", (_AS24_DE,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["priority"] == 1
    assert rows[0]["scheduled_at"] == _NOW + _HOUR
    assert sleeps == [30.0]


@pytest.mark.unit
def test_run_second_cycle_does_not_duplicate_pending_work(conn) -> None:
    sleeps: list[float] = []

    async def sleep(d: float) -> None:
        sleeps.append(d)

    cfg = SchedulerConfig(poll_interval_s=15.0)
    asyncio.run(
        scheduler.run(
            cfg,
            due_source=_source([_stats(_AS24_DE, "DE", changed=True)]),
            conn=conn,
            sleep=sleep,
            now_fn=lambda: _NOW,
            max_cycles=2,
        )
    )

    # Cycle 1 enqueues; cycle 2 sees has_pending → no second row.
    assert conn.execute("SELECT COUNT(*) FROM work_queue").fetchone()[0] == 1
    assert sleeps == [15.0, 15.0]
