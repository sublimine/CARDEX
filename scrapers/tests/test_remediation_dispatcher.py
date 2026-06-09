"""
Remediation dispatcher — anti-churn routing (Bloque F self-healing).

Establishes test infra for the previously-untested dispatcher. Verifies that a volume_drift
alert past the MAX_REMEDIATIONS cap routes to the DLQ (anti-churn), and under the cap drives
remediate(). The cap counts recent re-scrapes by source_key (the fix: it used to count only by
entity_ulid, which is NULL for unregistered sources -> cap never fired -> livelock risk).
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.delta import remediation_dispatcher as rd


class _Conn:
    def __init__(self, count: int):
        self.count = count
        self.execs: list = []

    async def fetchval(self, sql, *a):
        if "source_entities" in sql and "country" in sql:
            return ""                       # country lookup
        if "count(*)" in sql.lower():
            return self.count               # _recent_remediations
        return None

    async def execute(self, sql, *a):
        self.execs.append((sql, a))         # _set_alert


class _Redis:
    def __init__(self):
        self.adds: list = []

    async def xadd(self, stream, fields, **k):
        self.adds.append((stream, fields))


@pytest.mark.unit
def test_volume_drift_past_cap_routes_to_dlq():
    conn = _Conn(count=rd.MAX_REMEDIATIONS)   # at/over the cap
    rdb = _Redis()
    f = {"alert_id": "1", "entity_ulid": "se_x", "source_key": "new-dealer.fr", "signal": "volume_drift"}
    out = asyncio.run(rd.handle_event(conn, rdb, f, deps_provider=lambda: {}))
    assert out["action"] == "dlq"
    assert out["attempts"] == rd.MAX_REMEDIATIONS
    assert any("dlq" in str(stream).lower() for stream, _ in rdb.adds)   # parked on DLQ


@pytest.mark.unit
def test_volume_drift_under_cap_remediates():
    conn = _Conn(count=0)
    rdb = _Redis()
    f = {"alert_id": "2", "entity_ulid": "se_y", "source_key": "dealer2.fr", "signal": "volume_drift"}

    class _Res:
        recovered = True
        persisted = 5
        version = 2
        new_strategy = None
        strategy_changed = False
        notes = ()

    async def fake_remediate(source_key, country, **deps):
        return _Res()

    out = asyncio.run(rd.handle_event(conn, rdb, f, deps_provider=lambda: {"x": 1}, remediate_fn=fake_remediate))
    assert out["action"] == "remediate"
    assert out["recovered"] is True


@pytest.mark.unit
def test_waf_block_escalates_without_remediating():
    conn = _Conn(count=0)
    rdb = _Redis()
    f = {"alert_id": "3", "entity_ulid": "se_z", "source_key": "datadome-giant.fr", "signal": "waf_block"}
    out = asyncio.run(rd.handle_event(conn, rdb, f, deps_provider=lambda: {}))
    assert out["action"] == "mark_requires_proxy"   # waf -> escalate, never auto-loop
