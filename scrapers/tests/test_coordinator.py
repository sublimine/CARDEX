"""
Coordinator tests — pure decisions + work_queue ops + one-job orchestration + loop.

Three layers, mirroring coordinator.py:

  * Pure decisions (`is_success`, `circuit_action_for`, `next_queue_state`) are pinned
    with hand-picked inputs — no DB, no clock.
  * The work_queue DB ops (`claim_next`, `mark_done`, `mark_failed`, `requeue`,
    `apply_circuit_outcome`, `sync_runtime_gauges`) run against the in-memory `conn`.
  * `_process_item` / `run` orchestration is exercised with injected seams: a fake
    `session_factory`, a monkeypatched `get_scraper` returning a programmable scraper,
    and a bounded fake clock — so nothing touches curl_cffi / asyncpg / redis. This is
    the whole point of the design (the prior system cost two months by being testable
    only against live infra — directive #7).

Coroutines run synchronously with asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers import coordinator
from scrapers.coordinator import (
    MAX_ATTEMPTS,
    CoordinatorConfig,
    QueueOutcome,
    apply_circuit_outcome,
    circuit_action_for,
    claim_next,
    is_success,
    mark_done,
    mark_failed,
    next_queue_state,
    requeue,
    sync_runtime_gauges,
    _CIRCUIT_OPEN_BACKOFF_S,
    _NO_IDENTITY_BACKOFF_S,
    _SOFT_BLOCK_BACKOFF_S,
)
from scrapers.pipeline import dlq
from scrapers.pipeline.dlq import DlqReason
from scrapers.portals.base import RunResult, RunStatus

_NOW = 1_000_000
_AS24_DE = "autoscout24.de"


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _FakeScraper:
    """Programmable stand-in for a registered portal scraper."""

    def __init__(self, result: RunResult, *, domain: str = _AS24_DE, country: str = "DE") -> None:
        self.DOMAIN = domain
        self.COUNTRY = country
        self._result = result
        self.run_calls: list[tuple[Any, Any]] = []

    async def run(self, conn, session, *, on_urls=None) -> RunResult:
        self.run_calls.append((session, on_urls))
        return self._result


class _AsyncCloseSession:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _SyncCloseSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _insert_job(
    conn,
    *,
    job_id: str,
    portal: str = _AS24_DE,
    country: str = "DE",
    priority: int = 5,
    attempts: int = 0,
    scheduled_at: int = 0,
    status: str = "pending",
    created_at: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO work_queue (id, portal, country, status, priority, attempts, created_at, scheduled_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, portal, country, status, priority, attempts, created_at, scheduled_at),
    )


def _row(conn, job_id: str):
    return conn.execute("SELECT * FROM work_queue WHERE id = ?", (job_id,)).fetchone()


def _process(conn, item, *, session_factory, sink_factory=None, now=_NOW) -> None:
    asyncio.run(
        coordinator._process_item(
            conn, item, session_factory=session_factory, sink_factory=sink_factory, now=now
        )
    )


# --------------------------------------------------------------------------- #
# pure decisions
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_success_only_for_ok() -> None:
    assert is_success(RunStatus.OK) is True
    for s in (
        RunStatus.CIRCUIT_OPEN, RunStatus.NO_IDENTITY,
        RunStatus.SOFT_BLOCKED, RunStatus.EMPTY_SUSPECT,
    ):
        assert is_success(s) is False


@pytest.mark.unit
def test_circuit_action_for_each_status() -> None:
    assert circuit_action_for(RunStatus.OK) == "success"
    assert circuit_action_for(RunStatus.SOFT_BLOCKED) == "failure"
    assert circuit_action_for(RunStatus.CIRCUIT_OPEN) == "none"
    assert circuit_action_for(RunStatus.NO_IDENTITY) == "none"
    # Harvest-0 leaves the breaker untouched: it may be a genuinely empty portal,
    # not a tier failure, so it must not escalate the circuit.
    assert circuit_action_for(RunStatus.EMPTY_SUSPECT) == "none"


@pytest.mark.unit
def test_next_queue_state_ok_is_done() -> None:
    assert next_queue_state(RunStatus.OK, 0, max_attempts=MAX_ATTEMPTS) == QueueOutcome(
        action="done", increment_attempt=False
    )


@pytest.mark.unit
def test_next_queue_state_soft_block_retries_then_consumes_attempt() -> None:
    out = next_queue_state(RunStatus.SOFT_BLOCKED, 0, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(
        action="retry", increment_attempt=True, backoff_s=_SOFT_BLOCK_BACKOFF_S, error="soft_block"
    )


@pytest.mark.unit
def test_next_queue_state_soft_block_becomes_terminal_at_max() -> None:
    # attempts already 2; this run makes the 3rd → terminal failure.
    out = next_queue_state(RunStatus.SOFT_BLOCKED, MAX_ATTEMPTS - 1, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(action="failed", increment_attempt=True, error="soft_block")


@pytest.mark.unit
def test_next_queue_state_empty_suspect_retries_then_consumes_attempt() -> None:
    out = next_queue_state(RunStatus.EMPTY_SUSPECT, 0, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(
        action="retry", increment_attempt=True, backoff_s=_SOFT_BLOCK_BACKOFF_S, error="empty_harvest"
    )


@pytest.mark.unit
def test_next_queue_state_empty_suspect_becomes_terminal_at_max() -> None:
    out = next_queue_state(RunStatus.EMPTY_SUSPECT, MAX_ATTEMPTS - 1, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(action="failed", increment_attempt=True, error="empty_harvest")


@pytest.mark.unit
def test_next_queue_state_circuit_open_retries_without_consuming_attempt() -> None:
    out = next_queue_state(RunStatus.CIRCUIT_OPEN, 2, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(
        action="retry", increment_attempt=False, backoff_s=_CIRCUIT_OPEN_BACKOFF_S, error="circuit_open"
    )


@pytest.mark.unit
def test_next_queue_state_no_identity_retries_without_consuming_attempt() -> None:
    out = next_queue_state(RunStatus.NO_IDENTITY, 2, max_attempts=MAX_ATTEMPTS)
    assert out == QueueOutcome(
        action="retry", increment_attempt=False, backoff_s=_NO_IDENTITY_BACKOFF_S, error="no_identity"
    )


# --------------------------------------------------------------------------- #
# claim_next — atomic claim + ordering
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_claim_next_returns_none_on_empty_queue(conn) -> None:
    assert claim_next(conn, _NOW) is None


@pytest.mark.unit
def test_claim_next_flips_pending_to_running(conn) -> None:
    _insert_job(conn, job_id="j1", scheduled_at=10)
    claimed = claim_next(conn, _NOW)
    assert claimed is not None and claimed["id"] == "j1"
    row = _row(conn, "j1")
    assert row["status"] == "running"
    assert row["started_at"] == _NOW


@pytest.mark.unit
def test_claim_next_honours_priority_then_scheduled_at(conn) -> None:
    _insert_job(conn, job_id="low", priority=5, scheduled_at=10)
    _insert_job(conn, job_id="high", priority=1, scheduled_at=20)
    # priority ASC wins regardless of scheduled_at.
    assert claim_next(conn, _NOW)["id"] == "high"
    assert claim_next(conn, _NOW)["id"] == "low"
    assert claim_next(conn, _NOW) is None


@pytest.mark.unit
def test_claim_next_breaks_priority_ties_by_oldest_scheduled(conn) -> None:
    _insert_job(conn, job_id="newer", priority=5, scheduled_at=50)
    _insert_job(conn, job_id="older", priority=5, scheduled_at=10)
    assert claim_next(conn, _NOW)["id"] == "older"


@pytest.mark.unit
def test_claim_next_skips_future_scheduled_jobs(conn) -> None:
    _insert_job(conn, job_id="future", scheduled_at=_NOW + 5_000)
    assert claim_next(conn, _NOW) is None


@pytest.mark.unit
def test_claim_next_ignores_non_pending_rows(conn) -> None:
    _insert_job(conn, job_id="running", status="running", scheduled_at=10)
    assert claim_next(conn, _NOW) is None


# --------------------------------------------------------------------------- #
# queue writers
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_mark_done_sets_status_and_clears_error(conn) -> None:
    _insert_job(conn, job_id="j1", status="running")
    conn.execute("UPDATE work_queue SET last_error='stale' WHERE id='j1'")
    mark_done(conn, "j1", now=_NOW)
    row = _row(conn, "j1")
    assert row["status"] == "done"
    assert row["completed_at"] == _NOW
    assert row["last_error"] is None


@pytest.mark.unit
def test_mark_failed_increments_attempt_when_requested(conn) -> None:
    _insert_job(conn, job_id="j1", status="running", attempts=1)
    mark_failed(conn, "j1", "boom", increment_attempt=True, now=_NOW)
    row = _row(conn, "j1")
    assert row["status"] == "failed"
    assert row["attempts"] == 2
    assert row["last_error"] == "boom"
    assert row["completed_at"] == _NOW


@pytest.mark.unit
def test_mark_failed_preserves_attempt_when_not_incrementing(conn) -> None:
    _insert_job(conn, job_id="j1", status="running", attempts=1)
    mark_failed(conn, "j1", "config", increment_attempt=False, now=_NOW)
    assert _row(conn, "j1")["attempts"] == 1


@pytest.mark.unit
def test_requeue_returns_job_to_pending_and_clears_running_marker(conn) -> None:
    _insert_job(conn, job_id="j1", status="running", attempts=0)
    conn.execute("UPDATE work_queue SET started_at=? WHERE id='j1'", (_NOW,))
    requeue(conn, "j1", scheduled_at=_NOW + 500, error="soft_block", increment_attempt=True)
    row = _row(conn, "j1")
    assert row["status"] == "pending"
    assert row["scheduled_at"] == _NOW + 500
    assert row["started_at"] is None
    assert row["last_error"] == "soft_block"
    assert row["attempts"] == 1


# --------------------------------------------------------------------------- #
# apply_circuit_outcome
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_apply_circuit_outcome_records_success(conn) -> None:
    state = apply_circuit_outcome(conn, _AS24_DE, "T2", RunStatus.OK)
    assert state == "closed"
    row = conn.execute(
        "SELECT last_success FROM domain_tier_state WHERE domain=? AND tier='T2'", (_AS24_DE,)
    ).fetchone()
    assert row is not None and row["last_success"] is not None


@pytest.mark.unit
def test_apply_circuit_outcome_records_failure(conn) -> None:
    state = apply_circuit_outcome(conn, _AS24_DE, "T2", RunStatus.SOFT_BLOCKED)
    assert state == "closed"  # a single failure is below the open threshold
    row = conn.execute(
        "SELECT fail_count, last_fail FROM domain_tier_state WHERE domain=? AND tier='T2'", (_AS24_DE,)
    ).fetchone()
    assert row["fail_count"] == 1 and row["last_fail"] is not None


@pytest.mark.unit
def test_apply_circuit_outcome_none_for_transient_statuses(conn) -> None:
    assert apply_circuit_outcome(conn, _AS24_DE, "T2", RunStatus.CIRCUIT_OPEN) is None
    assert apply_circuit_outcome(conn, _AS24_DE, "T2", RunStatus.NO_IDENTITY) is None
    # Transient outcomes never touched the breaker table.
    assert conn.execute("SELECT COUNT(*) FROM domain_tier_state").fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# sync_runtime_gauges
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_sync_runtime_gauges_reads_dlq_size_without_error(conn) -> None:
    dlq.record_failure(conn, url="https://x/1", portal=_AS24_DE, reason=DlqReason.FETCH_ERROR)
    assert dlq.size(conn) == 1
    sync_runtime_gauges(conn)  # must not raise (metrics degrade gracefully)


# --------------------------------------------------------------------------- #
# _process_item — one job, all branches
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_process_item_unregistered_portal_fails_terminally(conn) -> None:
    _insert_job(conn, job_id="j1", portal="unknown.example", country="DE")
    item = _row(conn, "j1")

    async def session_factory(c, s):  # must never be reached
        raise AssertionError("session_factory called for unregistered portal")

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "failed"
    assert row["last_error"] == "unregistered_portal"
    assert row["attempts"] == 0  # config error never consumes a retry


@pytest.mark.unit
def test_process_item_non_car_portal_skipped_without_harvest(conn) -> None:
    # P1.5 scope guard: a non-car portal (truckscout24 trucks) is marked done
    # WITHOUT building a session / harvesting, so it never re-pollutes the car index.
    _insert_job(conn, job_id="jtruck", portal="truckscout24.com", country="DE")
    item = _row(conn, "jtruck")

    async def session_factory(c, s):  # must never be reached
        raise AssertionError("session_factory called for non-car portal")

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "jtruck")
    assert row["status"] == "done"
    assert row["attempts"] == 0


@pytest.mark.unit
def test_process_item_no_session_backs_off_without_running_scraper(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", attempts=0)
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.OK, tier="T2"))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)

    async def session_factory(c, s):
        return None

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "pending"  # retried
    assert row["scheduled_at"] == _NOW + _NO_IDENTITY_BACKOFF_S
    assert row["attempts"] == 0
    assert row["last_error"] == "no_identity"
    assert fake.run_calls == []  # scraper never invoked
    assert conn.execute("SELECT COUNT(*) FROM domain_tier_state").fetchone()[0] == 0


@pytest.mark.unit
def test_process_item_ok_marks_done_records_success_and_closes_session(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", attempts=0)
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.OK, tier="T2", url_count=1))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)
    session = _AsyncCloseSession()

    async def session_factory(c, s):
        return session

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "done"
    assert row["completed_at"] == _NOW
    assert row["last_error"] is None
    assert len(fake.run_calls) == 1
    assert session.closed is True
    cb = conn.execute(
        "SELECT circuit_state FROM domain_tier_state WHERE domain=? AND tier='T2'", (_AS24_DE,)
    ).fetchone()
    assert cb is not None and cb["circuit_state"] == "closed"


@pytest.mark.unit
def test_process_item_soft_block_retries_and_records_failure(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", attempts=0)
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.SOFT_BLOCKED, tier="T2"))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)
    session = _AsyncCloseSession()

    async def session_factory(c, s):
        return session

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "pending"
    assert row["scheduled_at"] == _NOW + _SOFT_BLOCK_BACKOFF_S
    assert row["attempts"] == 1            # soft block consumes an attempt
    assert row["last_error"] == "soft_block"
    assert session.closed is True
    cb = conn.execute(
        "SELECT fail_count FROM domain_tier_state WHERE domain=? AND tier='T2'", (_AS24_DE,)
    ).fetchone()
    assert cb["fail_count"] == 1


@pytest.mark.unit
def test_process_item_soft_block_at_max_attempts_fails_terminally(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", attempts=MAX_ATTEMPTS - 1)
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.SOFT_BLOCKED, tier="T2"))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)

    async def session_factory(c, s):
        return _AsyncCloseSession()

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "failed"
    assert row["attempts"] == MAX_ATTEMPTS
    assert row["last_error"] == "soft_block"


@pytest.mark.unit
def test_process_item_circuit_open_retries_without_touching_breaker(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", attempts=1)
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.CIRCUIT_OPEN, tier="T3"))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)

    async def session_factory(c, s):
        return _AsyncCloseSession()

    _process(conn, item, session_factory=session_factory)

    row = _row(conn, "j1")
    assert row["status"] == "pending"
    assert row["scheduled_at"] == _NOW + _CIRCUIT_OPEN_BACKOFF_S
    assert row["attempts"] == 1  # transient infra → no attempt burned
    assert row["last_error"] == "circuit_open"
    # action == "none" → no breaker write
    assert conn.execute("SELECT COUNT(*) FROM domain_tier_state").fetchone()[0] == 0


@pytest.mark.unit
def test_process_item_builds_and_passes_sink_to_scraper(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1")
    item = _row(conn, "j1")
    fake = _FakeScraper(RunResult(RunStatus.OK, tier="T2"))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)
    sentinel_sink = object()

    def sink_factory(scraper):
        assert scraper is fake
        return sentinel_sink

    async def session_factory(c, s):
        return _AsyncCloseSession()

    _process(conn, item, session_factory=session_factory, sink_factory=sink_factory)

    assert fake.run_calls[0][1] is sentinel_sink  # the sink reached scraper.run


# --------------------------------------------------------------------------- #
# _close_session
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_close_session_awaits_async_closer() -> None:
    s = _AsyncCloseSession()
    asyncio.run(coordinator._close_session(s))
    assert s.closed is True


@pytest.mark.unit
def test_close_session_calls_sync_closer() -> None:
    s = _SyncCloseSession()
    asyncio.run(coordinator._close_session(s))
    assert s.closed is True


@pytest.mark.unit
def test_close_session_noop_when_no_closer() -> None:
    asyncio.run(coordinator._close_session(object()))  # must not raise


# --------------------------------------------------------------------------- #
# run — bounded main loop
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_processes_due_job_without_sleeping(conn, monkeypatch) -> None:
    _insert_job(conn, job_id="j1", scheduled_at=0)
    fake = _FakeScraper(RunResult(RunStatus.OK, tier="T2", url_count=1))
    monkeypatch.setattr(coordinator, "get_scraper", lambda d: fake)
    session = _AsyncCloseSession()
    sleeps: list[float] = []

    async def session_factory(c, s):
        return session

    async def sleep(d: float) -> None:
        sleeps.append(d)

    cfg = CoordinatorConfig(prometheus_port=0, work_poll_interval_s=5.0)
    asyncio.run(
        coordinator.run(
            cfg, session_factory=session_factory, sink_factory=None,
            conn=conn, sleep=sleep, now_fn=lambda: _NOW, max_cycles=1,
        )
    )

    assert _row(conn, "j1")["status"] == "done"
    assert sleeps == []  # had work → never idled
    assert session.closed is True


@pytest.mark.unit
def test_run_sleeps_when_queue_idle(conn) -> None:
    sleeps: list[float] = []

    async def session_factory(c, s):  # never reached on an idle queue
        raise AssertionError("session_factory called while idle")

    async def sleep(d: float) -> None:
        sleeps.append(d)

    cfg = CoordinatorConfig(prometheus_port=0, work_poll_interval_s=7.0)
    asyncio.run(
        coordinator.run(
            cfg, session_factory=session_factory, conn=conn,
            sleep=sleep, now_fn=lambda: _NOW, max_cycles=2,
        )
    )

    assert sleeps == [7.0, 7.0]


# ── drift gate wiring (resilience: live volume-drift detection) ────────────────
@pytest.mark.unit
def test_check_volume_drift_alerts_below_baseline():
    # autotrack.nl config baseline is a 1000 full-harvest floor.
    report = coordinator.check_volume_drift("autotrack.nl", 50)
    assert report is not None and report.alert and not report.volume_ok


@pytest.mark.unit
def test_check_volume_drift_ok_above_baseline():
    report = coordinator.check_volume_drift("autotrack.nl", 50_000)
    assert report is not None and report.ok


@pytest.mark.unit
def test_check_volume_drift_none_when_no_config():
    # drift detection is opt-in per portal: no config → no baseline → None.
    assert coordinator.check_volume_drift("no-such-portal.invalid", 0) is None
