"""
Coordinator — orchestrator principal del scraping engine.

Consumes `work_queue`, runs the registered portal scraper for each claimed job,
and translates the outcome into circuit-breaker state, queue lifecycle, and
Prometheus gauges. The cross-cutting scrape mechanics (tier selection, identity
allocation, pagination, soft-block detection, trust accounting, the success
metric) already live in `BasePortalScraper.run`; the coordinator owns only what
sits *around* one run: claiming work atomically, the circuit-breaker outcome, the
queue state machine, the dlq-size / circuit-state gauges, and quarantine release.

Testability is the design constraint (the prior system cost two months by being
testable only against live infra). Every decision is a pure function and every
piece of live infrastructure is reached through an injected seam:

  * `session_factory(conn, scraper)` builds the curl_cffi/Camoufox session
    (`make_live_session`) — returns None when no eligible identity exists.
  * `sink_factory(scraper)` builds the URL sink that runs the PG/Redis delta
    (`make_live_sink_factory`).
  * `conn`, `sleep`, `now_fn`, `max_cycles` let a test drive the loop with an
    in-memory DB and a fake clock.

`run()` takes the seams; `main()` wires the live ones. Importing this module pulls
no curl_cffi / asyncpg / redis — those land only inside the seam bodies — so the
whole engine collects under pytest without the network stack installed.

Entry point: `python -m scrapers.coordinator`
Config via env vars: DATABASE_URL, REDIS_URL, ENGINE_DB_PATH, PROMETHEUS_PORT
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from scrapers.db import connect, migrate
from scrapers.engine.identity import store as identity_store
from scrapers.engine.identity.aging import release_quarantine
from scrapers.engine.monitoring import metrics
from scrapers.engine.proxy import tiers as proxy_tiers
from scrapers.engine.router import circuit, escalator
from scrapers.engine.router.domain_map import Tier
from scrapers.pipeline import dlq
from scrapers.portals import get_scraper
from scrapers.portals.base import RunStatus, UrlSink

log = logging.getLogger(__name__)

# Queue lifecycle — SCRAPING_ENGINE.md §C4 / work_queue retry policy.
MAX_ATTEMPTS = 3
_PREMIUM_TRUST = 7.0  # T3 (DataDome) is premium-only (§A1, mirrors base._PREMIUM_TRUST)

# Retry backoffs (seconds) by failure class. A soft block consumes an attempt
# (the identity is burning, escalate toward terminal); a circuit-open or missing
# identity is transient infrastructure, so it backs off WITHOUT consuming one.
_SOFT_BLOCK_BACKOFF_S = 3_600   # 1h — let the identity rest / a fresh one warm
_CIRCUIT_OPEN_BACKOFF_S = 120   # matches the breaker's open duration
_NO_IDENTITY_BACKOFF_S = 1_800  # 30m — give warming time to produce an identity

SessionFactory = Callable[[sqlite3.Connection, Any], Awaitable[Any]]
SinkFactory = Callable[[Any], UrlSink]


@dataclass
class CoordinatorConfig:
    db_path: str = "scrapers/engine.db"
    database_url: str = "postgres://cardex:cardex_dev_only@localhost:5432/cardex"
    redis_url: str = "redis://localhost:6379"
    curl_cffi_workers: int = 3       # T1 concurrent workers
    camoufox_pool_size: int = 8      # T2 concurrent browsers
    camoufox_t3_pool_size: int = 3   # T3 concurrent browsers (behavioral)
    prometheus_port: int = 9090
    work_poll_interval_s: float = 5.0

    @classmethod
    def from_env(cls) -> "CoordinatorConfig":
        """
        Build config from the documented env vars, keeping each default when the
        var is unset. Honors the module-header contract (DATABASE_URL, REDIS_URL,
        ENGINE_DB_PATH, PROMETHEUS_PORT): without this, `python -m
        scrapers.coordinator` silently ignored those overrides and always bound the
        hardcoded localhost:6379 / :9090 — so a host where the Docker Redis isn't
        published, or where Prometheus already holds :9090, could never run the
        live loop. PROMETHEUS_PORT=0 disables the exporter (run() skips a falsy
        port), which is the clean way to avoid a bind clash on a busy host.
        """
        overrides: dict[str, Any] = {}
        if db_path := os.environ.get("ENGINE_DB_PATH"):
            overrides["db_path"] = db_path
        if database_url := os.environ.get("DATABASE_URL"):
            overrides["database_url"] = database_url
        if redis_url := os.environ.get("REDIS_URL"):
            overrides["redis_url"] = redis_url
        if (prometheus_port := os.environ.get("PROMETHEUS_PORT")) is not None:
            overrides["prometheus_port"] = int(prometheus_port)
        return cls(**overrides)


# ── pure decisions (no I/O) ───────────────────────────────────────────────────
def is_success(status: RunStatus) -> bool:
    return status is RunStatus.OK


def circuit_action_for(status: RunStatus) -> str:
    """
    Which breaker transition a run outcome implies.

    OK confirms the tier works (record_success). A soft block is the breaker's
    failure signal (record_failure). CIRCUIT_OPEN / NO_IDENTITY never reached the
    network, so they leave the breaker untouched ("none").
    """
    if status is RunStatus.OK:
        return "success"
    if status is RunStatus.SOFT_BLOCKED:
        return "failure"
    return "none"


@dataclass(frozen=True)
class QueueOutcome:
    """What to do with a work_queue row after one run."""

    action: str  # "done" | "failed" | "retry"
    increment_attempt: bool
    backoff_s: int | None = None
    error: str | None = None


def next_queue_state(status: RunStatus, attempts: int, *, max_attempts: int) -> QueueOutcome:
    """
    Map a run outcome + the attempts already spent to the next queue state (pure).

    OK → done. A soft block consumes an attempt and retries in 1h, becoming a
    terminal failure once attempts are exhausted. A circuit-open or missing
    identity is transient: it retries on its own backoff WITHOUT consuming an
    attempt, so infrastructure hiccups never burn a job's retry budget.
    """
    if status is RunStatus.OK:
        return QueueOutcome(action="done", increment_attempt=False)
    if status is RunStatus.SOFT_BLOCKED:
        if attempts + 1 >= max_attempts:
            return QueueOutcome(action="failed", increment_attempt=True, error="soft_block")
        return QueueOutcome(
            action="retry", increment_attempt=True, backoff_s=_SOFT_BLOCK_BACKOFF_S, error="soft_block"
        )
    if status is RunStatus.CIRCUIT_OPEN:
        return QueueOutcome(
            action="retry", increment_attempt=False, backoff_s=_CIRCUIT_OPEN_BACKOFF_S, error="circuit_open"
        )
    return QueueOutcome(
        action="retry", increment_attempt=False, backoff_s=_NO_IDENTITY_BACKOFF_S, error="no_identity"
    )


# ── work_queue DB ops ─────────────────────────────────────────────────────────
def claim_next(conn: sqlite3.Connection, now: int | None = None) -> sqlite3.Row | None:
    """
    Atomically claim the highest-priority due job, or None when the queue is idle.

    Selects the best candidate (priority ASC, then oldest scheduled_at) then flips
    it pending→running under a guard. The guard + rowcount check is the concurrency
    primitive: if another worker won the race the UPDATE matches no row and we
    return None rather than double-processing. The returned snapshot predates the
    flip, which is fine — only id/portal/attempts are read downstream.
    """
    ts = int(time.time()) if now is None else now
    row = conn.execute(
        "SELECT * FROM work_queue WHERE status = 'pending' AND scheduled_at <= ? "
        "ORDER BY priority ASC, scheduled_at ASC LIMIT 1",
        (ts,),
    ).fetchone()
    if row is None:
        return None
    claimed = conn.execute(
        "UPDATE work_queue SET status = 'running', started_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (ts, row["id"]),
    )
    if claimed.rowcount != 1:
        return None  # lost the race to another worker
    return row


def mark_done(conn: sqlite3.Connection, job_id: str, *, now: int) -> None:
    conn.execute(
        "UPDATE work_queue SET status = 'done', completed_at = ?, last_error = NULL WHERE id = ?",
        (now, job_id),
    )


def mark_failed(
    conn: sqlite3.Connection, job_id: str, error: str, *, increment_attempt: bool, now: int
) -> None:
    bump = ", attempts = attempts + 1" if increment_attempt else ""
    conn.execute(
        f"UPDATE work_queue SET status = 'failed', completed_at = ?, last_error = ?{bump} WHERE id = ?",
        (now, error, job_id),
    )


def requeue(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    scheduled_at: int,
    error: str | None,
    increment_attempt: bool,
) -> None:
    """Return a job to pending for a later retry, clearing its running marker."""
    bump = ", attempts = attempts + 1" if increment_attempt else ""
    conn.execute(
        f"UPDATE work_queue SET status = 'pending', scheduled_at = ?, started_at = NULL, "
        f"last_error = ?{bump} WHERE id = ?",
        (scheduled_at, error, job_id),
    )


def apply_circuit_outcome(
    conn: sqlite3.Connection, domain: str, tier: str, status: RunStatus
) -> str | None:
    """Record the breaker transition for a run outcome; return the new state, or None."""
    action = circuit_action_for(status)
    if action == "success":
        return circuit.record_success(conn, domain, tier).value
    if action == "failure":
        return circuit.record_failure(conn, domain, tier).value
    return None


def sync_runtime_gauges(conn: sqlite3.Connection) -> None:
    """Refresh the per-cycle operational gauges the coordinator owns."""
    metrics.set_dlq_size(dlq.size(conn))


def _apply_queue_outcome(
    conn: sqlite3.Connection, job_id: str, outcome: QueueOutcome, *, now: int
) -> None:
    if outcome.action == "done":
        mark_done(conn, job_id, now=now)
    elif outcome.action == "failed":
        mark_failed(conn, job_id, outcome.error or "", increment_attempt=outcome.increment_attempt, now=now)
    else:  # retry
        requeue(
            conn,
            job_id,
            scheduled_at=now + (outcome.backoff_s or 0),
            error=outcome.error,
            increment_attempt=outcome.increment_attempt,
        )


# ── one job ───────────────────────────────────────────────────────────────────
async def _process_item(
    conn: sqlite3.Connection,
    item: sqlite3.Row,
    *,
    session_factory: SessionFactory,
    sink_factory: SinkFactory | None,
    now: int,
) -> None:
    """Run one claimed job and persist its circuit + queue consequences."""
    domain = item["portal"]
    scraper = get_scraper(domain)
    if scraper is None:
        log.error("no scraper registered for portal %s — failing terminally", domain)
        mark_failed(conn, item["id"], "unregistered_portal", increment_attempt=False, now=now)
        return

    session = await session_factory(conn, scraper)
    if session is None:
        # No eligible identity to even build a session — mirror NO_IDENTITY without
        # invoking the scraper, and back off without consuming an attempt.
        outcome = next_queue_state(RunStatus.NO_IDENTITY, item["attempts"], max_attempts=MAX_ATTEMPTS)
        _apply_queue_outcome(conn, item["id"], outcome, now=now)
        return

    try:
        sink = sink_factory(scraper) if sink_factory is not None else None
        result = await scraper.run(conn, session, on_urls=sink)
    finally:
        await _close_session(session)

    state = apply_circuit_outcome(conn, domain, result.tier, result.status)
    if state is not None:
        metrics.set_circuit_state(domain, result.tier, state)

    outcome = next_queue_state(result.status, item["attempts"], max_attempts=MAX_ATTEMPTS)
    _apply_queue_outcome(conn, item["id"], outcome, now=now)


async def _safe_process_item(
    conn: sqlite3.Connection,
    item: sqlite3.Row,
    *,
    session_factory: SessionFactory,
    sink_factory: SinkFactory | None,
    now: int,
) -> None:
    """
    Run one job, isolating any unhandled scraper error from the engine loop.

    BasePortalScraper.run does not wrap its live fetch, so a network/parse error
    in a single portal propagates. Without this guard it would unwind the whole
    coordinator loop, taking the other 70 portals down with it — and the job,
    already flipped pending->running by claim_next, would be stranded in 'running'
    forever (claim_next only re-picks 'pending'). Here a crash is treated like a
    consumed-attempt transient fault: log it, back the job off for a retry, and let
    it go terminal after MAX_ATTEMPTS so a deterministically broken portal can't
    hot-loop. The loop then advances to the next job.
    """
    try:
        await _process_item(
            conn, item, session_factory=session_factory, sink_factory=sink_factory, now=now
        )
    except Exception:  # noqa: BLE001 — one portal must never crash the engine
        log.exception("unhandled error scraping %s — isolating, requeueing", item["portal"])
        try:
            if item["attempts"] + 1 >= MAX_ATTEMPTS:
                mark_failed(conn, item["id"], "unhandled_exception", increment_attempt=True, now=now)
            else:
                requeue(
                    conn,
                    item["id"],
                    scheduled_at=now + _SOFT_BLOCK_BACKOFF_S,
                    error="unhandled_exception",
                    increment_attempt=True,
                )
        except Exception:  # noqa: BLE001 — never let cleanup bookkeeping crash the loop
            log.exception("failed to requeue %s after crash; leaving for recovery", item["portal"])


async def _close_session(session: Any) -> None:
    """Close an injected session, awaiting an async closer when there is one."""
    closer = getattr(session, "aclose", None) or getattr(session, "close", None)
    if closer is None:
        return
    result = closer()
    if inspect.isawaitable(result):
        await result


# ── main loop ─────────────────────────────────────────────────────────────────
async def run(
    config: CoordinatorConfig,
    *,
    session_factory: SessionFactory | None = None,
    sink_factory: SinkFactory | None = None,
    conn: sqlite3.Connection | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now_fn: Callable[[], float] = time.time,
    max_cycles: int | None = None,
) -> None:
    """
    Main loop. Never returns under normal operation (bounded by max_cycles in tests).

    Each cycle releases due quarantines, refreshes the runtime gauges, then claims
    and processes one job (sleeping when the queue is idle). Seams default to the
    live wiring; tests inject fakes plus a bounded clock.
    """
    owns_conn = conn is None
    if conn is None:
        conn = connect(config.db_path)
        migrate(conn)
    factory = session_factory or make_live_session
    if config.prometheus_port:
        metrics.start(config.prometheus_port)

    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            now = int(now_fn())
            release_quarantine(conn, now)
            sync_runtime_gauges(conn)
            item = claim_next(conn, now)
            if item is None:
                await sleep(config.work_poll_interval_s)
            else:
                await _safe_process_item(
                    conn, item, session_factory=factory, sink_factory=sink_factory, now=now
                )
            cycles += 1
    finally:
        if owns_conn:
            conn.close()


# ── live seams (only these touch curl_cffi / asyncpg / redis) ──────────────────
async def make_live_session(conn: sqlite3.Connection, scraper: Any) -> Any | None:
    """
    Build the curl_cffi session for `scraper`'s effective tier, or None if no
    eligible identity exists.

    Picks the identity with the SAME query `BasePortalScraper.run` will use
    (store.pick_for_portal, deterministic ORDER BY), so the session's JA3/proxy
    belong to the very identity the run then rewards — no identity/session drift.

    T0/T1 accept a DIRECT (no-proxy) identity; T2/T3 require a proxied one
    (proxy_tiers.requires_proxy), so with only direct identities provisioned a
    T2/T3 job finds none here → the coordinator parks it on NO_IDENTITY backoff.
    """
    tier = escalator.get_effective_tier(conn, scraper.DOMAIN)
    min_trust = _PREMIUM_TRUST if tier is Tier.T3 else 0.0
    identity = identity_store.pick_for_portal(
        conn,
        scraper.COUNTRY,
        scraper.DOMAIN,
        min_trust=min_trust,
        require_proxy=proxy_tiers.requires_proxy(tier),
    )
    if identity is None:
        return None
    from scrapers.engine.antidetect import tls  # lazy: pulls curl_cffi

    return tls.make_session(identity)


def make_live_sink_factory(pg: Any, rdb: Any) -> SinkFactory:
    """Build the per-scraper URL sink that runs the PG/Redis delta on collected links."""
    from scrapers.common import indexer  # lazy: pulls asyncpg + redis

    def factory(scraper: Any) -> UrlSink:
        async def sink(urls: list[str]) -> None:
            await indexer.delta(pg, rdb, scraper.DOMAIN, scraper.COUNTRY, scraper.DOMAIN, urls)

        return sink

    return factory


async def main(config: CoordinatorConfig | None = None) -> None:
    """Production entrypoint: wire the live PG/Redis seams and run the loop."""
    config = config or CoordinatorConfig.from_env()
    from scrapers.common import indexer  # lazy: pulls asyncpg + redis

    pg = await indexer.make_pg(config.database_url)
    rdb = await indexer.make_redis(config.redis_url)
    sink_factory = make_live_sink_factory(pg, rdb)
    try:
        await run(config, session_factory=make_live_session, sink_factory=sink_factory)
    finally:
        await rdb.aclose()
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
