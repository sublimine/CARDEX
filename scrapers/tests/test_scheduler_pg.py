"""
Tests for scheduler_pg — DueSource, writeback, seed_portals.

Uses in-memory fakes (no real PG) following the engine's testing convention:
pure decision functions get unit tests; I/O seams get tested against fakes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# ── Row-to-stats conversion (pure, no PG needed) ────────────────────────────

@dataclass
class _FakeRow:
    """Minimal duck-type of asyncpg.Record for _row_to_stats."""
    _data: dict[str, Any]
    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)


def _make_row(
    portal: str = "mobile.de",
    country: str = "DE",
    current_interval_h: float = 12.0,
    last_change_at: datetime | None = None,
    listings_delta: int = 0,
) -> _FakeRow:
    return _FakeRow({
        "portal": portal,
        "country": country,
        "current_interval_h": current_interval_h,
        "last_change_at": last_change_at,
        "listings_delta": listings_delta,
    })


class TestRowToStats:
    def test_no_change_null_last_change(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        row = _make_row(listings_delta=0, last_change_at=None)
        stats = _row_to_stats(row, now)
        assert stats.portal == "mobile.de"
        assert stats.country == "DE"
        assert stats.current_interval_h == 12.0
        assert stats.changed is False
        # NULL last_change → days_since_change > 7 (triggers relaxation)
        assert stats.days_since_change >= 8

    def test_change_detected(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        row = _make_row(listings_delta=42, last_change_at=datetime.now(timezone.utc))
        stats = _row_to_stats(row, now)
        assert stats.changed is True
        assert stats.days_since_change == 0

    def test_negative_delta_is_change(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        row = _make_row(listings_delta=-10)
        stats = _row_to_stats(row, now)
        assert stats.changed is True

    def test_old_change_counts_days(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        five_days_ago = datetime.fromtimestamp(now - 5 * 86400, tz=timezone.utc)
        row = _make_row(listings_delta=0, last_change_at=five_days_ago)
        stats = _row_to_stats(row, now)
        assert stats.changed is False
        assert stats.days_since_change == 5

    def test_ten_day_old_change(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        ten_days_ago = datetime.fromtimestamp(now - 10 * 86400, tz=timezone.utc)
        row = _make_row(listings_delta=0, last_change_at=ten_days_ago)
        stats = _row_to_stats(row, now)
        assert stats.days_since_change == 10

    def test_interval_passthrough(self):
        from scrapers.scheduler_pg import _row_to_stats
        now = int(time.time())
        row = _make_row(current_interval_h=48.0)
        stats = _row_to_stats(row, now)
        assert stats.current_interval_h == 48.0


# ── Initial interval per tier ────────────────────────────────────────────────

class TestInitialIntervals:
    def test_t0_interval(self):
        from scrapers.scheduler_pg import _INITIAL_INTERVAL_H
        from scrapers.engine.router.domain_map import Tier
        assert _INITIAL_INTERVAL_H[Tier.T0] == 6.0

    def test_t1_interval(self):
        from scrapers.scheduler_pg import _INITIAL_INTERVAL_H
        from scrapers.engine.router.domain_map import Tier
        assert _INITIAL_INTERVAL_H[Tier.T1] == 6.0

    def test_t2_interval(self):
        from scrapers.scheduler_pg import _INITIAL_INTERVAL_H
        from scrapers.engine.router.domain_map import Tier
        assert _INITIAL_INTERVAL_H[Tier.T2] == 12.0

    def test_t3_interval(self):
        from scrapers.scheduler_pg import _INITIAL_INTERVAL_H
        from scrapers.engine.router.domain_map import Tier
        assert _INITIAL_INTERVAL_H[Tier.T3] == 24.0


# ── Seed portals coverage ───────────────────────────────────────────────────

class TestSeedCoverage:
    """Verify that every registered portal maps to a known tier."""

    def test_all_portals_have_tier_mapping(self):
        from scrapers.portals import PORTAL_REGISTRY
        from scrapers.engine.router.domain_map import get as get_spec
        unmapped = []
        for domain in PORTAL_REGISTRY:
            spec = get_spec(domain)
            if spec is None:
                unmapped.append(domain)
        assert unmapped == [], f"Portals without domain_map entry: {unmapped}"

    def test_portal_count_matches_registry(self):
        from scrapers.portals import PORTAL_REGISTRY
        # At least 71 portals (may grow)
        assert len(PORTAL_REGISTRY) >= 71


# ── Bootstrap CLI (dry-run, no PG needed) ────────────────────────────────────

class TestBootstrapCLI:
    def test_seed_work_queue_dry_run(self):
        from scrapers.cli.bootstrap import _seed_work_queue
        count = _seed_work_queue("scrapers/engine.db", dry_run=True)
        assert count >= 71

    def test_sqlite_bootstrap_dry_run(self):
        from scrapers.cli.bootstrap import _bootstrap_sqlite
        stats = _bootstrap_sqlite("scrapers/engine.db", dry_run=True)
        assert "sqlite_version" in stats

    def test_seed_work_queue_in_memory(self):
        """Seed queue with in-memory SQLite — no real DB needed."""
        from scrapers.db import connect, migrate
        from scrapers.portals import PORTAL_REGISTRY
        from scrapers.scheduler import enqueue
        from scrapers.engine.router.domain_map import Tier, get as get_spec
        import time as _time

        conn = connect(":memory:")
        migrate(conn)
        now = int(_time.time())
        count = 0
        for domain, cls in PORTAL_REGISTRY.items():
            spec = get_spec(domain)
            tier = spec.tier if spec else Tier.T1
            enqueue(conn, portal=domain, country=cls.COUNTRY, tier=tier,
                    scheduled_at=now, priority=5, now=now)
            count += 1

        # Verify all were enqueued
        total = conn.execute("SELECT COUNT(*) FROM work_queue WHERE status='pending'").fetchone()[0]
        assert total == count
        assert total >= 71
        conn.close()


# ── Integration: scheduler plan_cycle with fake DueSource ────────────────────

class TestPlanCycleIntegration:
    """Ensure the DueSource contract integrates with plan_cycle."""

    def test_plan_cycle_with_inline_due_source(self):
        from scrapers.db import connect, migrate
        from scrapers.scheduler import (
            PortalChangeStats, SchedulerConfig, plan_cycle,
        )
        import time as _time

        conn = connect(":memory:")
        migrate(conn)
        now = int(_time.time())
        config = SchedulerConfig()

        def fake_source(_conn):
            return [
                PortalChangeStats(
                    portal="mobile.de", country="DE",
                    current_interval_h=12.0, changed=True,
                    days_since_change=0,
                ),
                PortalChangeStats(
                    portal="marktplaats.nl", country="NL",
                    current_interval_h=6.0, changed=False,
                    days_since_change=3,
                ),
            ]

        ids = plan_cycle(conn, config, fake_source, now=now)
        assert len(ids) == 2

        # Verify both are pending in work_queue
        rows = conn.execute(
            "SELECT portal, country, status FROM work_queue ORDER BY portal"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["portal"] == "marktplaats.nl"
        assert rows[1]["portal"] == "mobile.de"

        # Second call should skip (already pending)
        ids2 = plan_cycle(conn, config, fake_source, now=now)
        assert len(ids2) == 0

        conn.close()
