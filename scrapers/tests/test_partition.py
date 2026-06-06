"""vehicle_events monthly partition helpers — pure bounds + SQL generation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from scrapers.common.indexer import (
    _month_bounds,
    ensure_event_partitions,
    ensure_month_partition,
)


class FakeConn:
    """Captures executed SQL without a real database."""

    def __init__(self):
        self.sql: list[str] = []

    async def execute(self, query, *args):
        self.sql.append(query)


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.unit
def test_month_bounds_mid_month():
    start, end = _month_bounds(datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc))
    assert start == datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.mark.unit
def test_month_bounds_december_rolls_year():
    start, end = _month_bounds(datetime(2026, 12, 9, tzinfo=timezone.utc))
    assert start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.mark.unit
def test_ensure_month_partition_emits_correct_ddl():
    conn = FakeConn()
    name = _run(ensure_month_partition(conn, datetime(2026, 7, 4, tzinfo=timezone.utc)))
    assert name == "vehicle_events_2026_07"
    sql = conn.sql[0]
    assert "CREATE TABLE IF NOT EXISTS vehicle_events_2026_07 PARTITION OF vehicle_events" in sql
    assert "FROM ('2026-07-01') TO ('2026-08-01')" in sql


@pytest.mark.unit
def test_ensure_event_partitions_covers_current_and_next():
    conn = FakeConn()
    names = _run(ensure_event_partitions(conn, now=datetime(2026, 12, 20, tzinfo=timezone.utc)))
    # current (Dec 2026) + next (Jan 2027, year rolled)
    assert names == ["vehicle_events_2026_12", "vehicle_events_2027_01"]
    assert len(conn.sql) == 2
