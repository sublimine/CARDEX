"""
Scheduler — decide qué portal scrape cuándo y con qué parámetros.

Two layers, deliberately split so the policy is unit-testable without any live
infrastructure (directive: the previous system cost two months because it could
only be exercised against live infra):

  * Pure decision functions (`decide_schedule`, `decide_dispatch`) — no I/O. They
    encode the §C1 adaptive cadence and the dispatch gates (circuit breaker +
    premium quota) as referentially-transparent policy.
  * A thin loop (`plan_cycle` / `run`) that reads current per-portal state from an
    injected `due_source`, applies the policy, and writes `work_queue` rows.

`due_source` is a REQUIRED injected seam — there is intentionally no live-Postgres
default. The §C1 cadence inputs (current interval, last-change recency) live on
`vehicle_index` columns that `common.indexer.ensure_schema` does NOT create, so
fabricating a query here would assert a schema that does not exist. Production
wires a reader for those columns; tests inject an in-memory iterable. Persisting
the *new* interval back to PG is likewise the production reader/writeback layer's
responsibility — this module owns only the SQLite `work_queue`.

Scheduling adaptativo (§C1):
  Con cambio detectado:  interval = max(interval/2, 1h),  next_scrape = now + 1h
  Sin cambio >= 7 días:  interval = min(interval*1.5, 30d), next_scrape = now + interval
  Estable (sin disparo):  interval inalterado,            next_scrape = now + interval
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from scrapers.db import connect, migrate
from scrapers.engine.identity import store as identity_store
from scrapers.engine.router import circuit, escalator
from scrapers.engine.router.domain_map import Tier

log = logging.getLogger(__name__)

_HOUR_S = 3600
_STATIC_DAYS = 7  # days without a change before the cadence relaxes (§C1)
_PRIORITY_CHANGED = 1  # a portal with fresh changes jumps the queue
_PRIORITY_NORMAL = 5


@dataclass
class SchedulerConfig:
    db_path: str = "scrapers/engine.db"
    database_url: str = "postgres://cardex:cardex_dev_only@localhost:5432/cardex"
    min_interval_h: float = 1.0
    max_interval_h: float = 720.0    # 30 días
    poll_interval_s: float = 60.0
    min_premium_t3: int = 3          # premium identities required to dispatch a T3 job


# ── pure decisions (no I/O) ───────────────────────────────────────────────────
@dataclass(frozen=True)
class ScheduleDecision:
    """The §C1 outcome for one portal: its new cadence and the next scrape epoch."""

    interval_h: float
    next_scrape_at: int


def decide_schedule(
    current_h: float,
    *,
    changed: bool,
    days_since_change: int,
    now: int,
    min_h: float,
    max_h: float,
) -> ScheduleDecision:
    """
    Adaptive cadence (§C1). Pure: same inputs → same decision, no clock, no DB.

    A detected change halves the interval (floored at min_h) and pulls the next
    scrape forward to now+1h so the change is re-checked quickly. A portal static
    for >= 7 days has its interval grown by half (capped at max_h). Otherwise the
    interval is left untouched and the next scrape lands one interval out.
    """
    if changed:
        interval_h = max(current_h * 0.5, min_h)
        return ScheduleDecision(interval_h=interval_h, next_scrape_at=now + _HOUR_S)
    if days_since_change >= _STATIC_DAYS:
        interval_h = min(current_h * 1.5, max_h)
    else:
        interval_h = current_h
    return ScheduleDecision(interval_h=interval_h, next_scrape_at=now + int(interval_h * _HOUR_S))


@dataclass(frozen=True)
class DispatchDecision:
    """Whether a portal may be enqueued this cycle, with the gating reason."""

    should_enqueue: bool
    reason: str


def decide_dispatch(
    tier: Tier,
    *,
    circuit_open: bool,
    premium_count: int,
    min_premium: int = 3,
) -> DispatchDecision:
    """
    Dispatch gates (pure). An OPEN breaker blocks every tier. T3 (DataDome) is
    premium-only: it is held back until enough premium identities exist to sustain
    it, rather than degrading silently to a weaker tier.
    """
    if circuit_open:
        return DispatchDecision(should_enqueue=False, reason="circuit_open")
    if tier is Tier.T3 and premium_count < min_premium:
        return DispatchDecision(should_enqueue=False, reason="insufficient_premium")
    return DispatchDecision(should_enqueue=True, reason="ok")


@dataclass(frozen=True)
class PortalChangeStats:
    """One portal's §C1 cadence inputs, as read from the production index."""

    portal: str
    country: str
    current_interval_h: float
    changed: bool
    days_since_change: int


DueSource = Callable[[sqlite3.Connection], Iterable[PortalChangeStats]]


# ── work_queue writers ────────────────────────────────────────────────────────
def enqueue(
    conn: sqlite3.Connection,
    *,
    portal: str,
    country: str,
    tier: Tier,
    scheduled_at: int,
    priority: int,
    filter_params: str | None = None,
    now: int | None = None,
) -> str:
    """Insert one pending work_queue row and return its generated id."""
    ts = int(time.time()) if now is None else now
    job_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO work_queue "
        "(id, portal, country, tier, filter_params, status, priority, created_at, scheduled_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (job_id, portal, country, tier.value, filter_params, priority, ts, scheduled_at),
    )
    return job_id


def has_pending(conn: sqlite3.Connection, portal: str, country: str) -> bool:
    """True when this portal already has unfinished work (pending or running)."""
    row = conn.execute(
        "SELECT 1 FROM work_queue "
        "WHERE portal = ? AND country = ? AND status IN ('pending', 'running') LIMIT 1",
        (portal, country),
    ).fetchone()
    return row is not None


# ── planning ──────────────────────────────────────────────────────────────────
def plan_cycle(
    conn: sqlite3.Connection,
    config: SchedulerConfig,
    due_source: DueSource,
    *,
    now: int,
) -> list[str]:
    """
    Read due portals, apply the dispatch gates + §C1 cadence, enqueue work.

    Skips portals whose breaker is OPEN or whose tier lacks the premium quota, and
    skips any portal that still has unfinished work so a slow scrape is never piled
    on. Returns the ids of the rows enqueued this cycle.
    """
    enqueued: list[str] = []
    for stats in due_source(conn):
        tier = escalator.get_effective_tier(conn, stats.portal)
        gate = decide_dispatch(
            tier,
            circuit_open=circuit.is_open(conn, stats.portal, tier.value),
            premium_count=identity_store.premium_count(conn, stats.country),
            min_premium=config.min_premium_t3,
        )
        if not gate.should_enqueue:
            log.info("skip %s/%s tier=%s reason=%s", stats.portal, stats.country, tier.value, gate.reason)
            continue
        if has_pending(conn, stats.portal, stats.country):
            log.debug("skip %s/%s — work already queued", stats.portal, stats.country)
            continue

        decision = decide_schedule(
            stats.current_interval_h,
            changed=stats.changed,
            days_since_change=stats.days_since_change,
            now=now,
            min_h=config.min_interval_h,
            max_h=config.max_interval_h,
        )
        priority = _PRIORITY_CHANGED if stats.changed else _PRIORITY_NORMAL
        job_id = enqueue(
            conn,
            portal=stats.portal,
            country=stats.country,
            tier=tier,
            scheduled_at=decision.next_scrape_at,
            priority=priority,
            now=now,
        )
        enqueued.append(job_id)
    return enqueued


async def run(
    config: SchedulerConfig,
    *,
    due_source: DueSource,
    conn: sqlite3.Connection | None = None,
    sleep: Callable[[float], object] = asyncio.sleep,
    now_fn: Callable[[], float] = time.time,
    max_cycles: int | None = None,
) -> None:
    """
    Planning loop. Runs alongside the coordinator.

    Infrastructure is injected (`due_source`, `conn`, `sleep`, `now_fn`) so the
    loop is exercised in tests with an in-memory DB and a synchronous fake clock;
    `max_cycles` bounds it for those tests. Production passes a real `due_source`.
    """
    owns_conn = conn is None
    if conn is None:
        conn = connect(config.db_path)
        migrate(conn)
    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            now = int(now_fn())
            plan_cycle(conn, config, due_source, now=now)
            await sleep(config.poll_interval_s)
            cycles += 1
    finally:
        if owns_conn:
            conn.close()
