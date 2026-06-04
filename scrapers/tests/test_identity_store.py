"""Identity store — upsert, selection priority, trust transitions."""
from __future__ import annotations

import dataclasses
import time

import pytest

from scrapers.engine.identity import store
from scrapers.engine.identity.profile import IdentityStatus


@pytest.mark.unit
def test_save_get_round_trip(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    got = store.get(conn, idy.id)
    assert got is not None
    assert got.id == idy.id
    assert got.country == "DE"
    assert got.fingerprint.user_agent == idy.fingerprint.user_agent
    assert got.proxy_tier == idy.proxy_tier


@pytest.mark.unit
def test_save_is_upsert(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    updated = dataclasses.replace(idy, trust_score=4.2, request_count=99)
    store.save(conn, updated)
    rows = conn.execute("SELECT COUNT(*) AS n FROM identities").fetchone()
    assert rows["n"] == 1  # upsert, not a second row
    got = store.get(conn, idy.id)
    assert got.trust_score == 4.2
    assert got.request_count == 99


@pytest.mark.unit
def test_get_missing_returns_none(conn):
    assert store.get(conn, "does-not-exist") is None


@pytest.mark.unit
def test_update_trust_quarantine_threshold(conn, active_identity):
    store.update_trust(conn, active_identity.id, -1.5)  # 1.0 - 1.5 = -0.5 < 0
    got = store.get(conn, active_identity.id)
    assert got.status == IdentityStatus.QUARANTINE
    assert got.quarantine_until is not None
    assert got.quarantine_until > int(time.time())


@pytest.mark.unit
def test_update_trust_retire_threshold(conn, active_identity):
    store.update_trust(conn, active_identity.id, -7.0)  # 1.0 - 7.0 = -6.0 < -5
    got = store.get(conn, active_identity.id)
    assert got.status == IdentityStatus.RETIRED
    assert got.retired_at is not None
    assert got.retire_reason == "trust_collapsed"


@pytest.mark.unit
def test_retired_is_terminal(conn, active_identity):
    store.update_trust(conn, active_identity.id, -7.0)  # retire
    store.update_trust(conn, active_identity.id, +5.0)  # must be ignored
    got = store.get(conn, active_identity.id)
    assert got.status == IdentityStatus.RETIRED


@pytest.mark.unit
def test_pick_for_portal_requires_warming(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    conn.execute(
        "UPDATE identities SET status='active', warming_done=0 WHERE id=?", (idy.id,)
    )
    assert store.pick_for_portal(conn, "DE", "autoscout24.de") is None


@pytest.mark.unit
def test_pick_for_portal_affinity_wins(conn, make_identity):
    # Two warmed active DE identities; the one holding an _abck for the domain wins
    # even with a lower trust_score.
    a = make_identity(identity_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", proxy_ip="203.0.113.1")
    b = make_identity(identity_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", proxy_ip="203.0.113.2")
    store.save(conn, a)
    store.save(conn, b)
    conn.execute(
        "UPDATE identities SET status='active', warming_done=1, trust_score=9.0 WHERE id=?",
        (a.id,),
    )
    conn.execute(
        "UPDATE identities SET status='active', warming_done=1, trust_score=1.0, "
        "abck_tokens='{\"autoscout24.de\": \"~0~abck~token\"}' WHERE id=?",
        (b.id,),
    )
    picked = store.pick_for_portal(conn, "DE", "autoscout24.de")
    assert picked is not None
    assert picked.id == b.id  # affinity beats higher trust


@pytest.mark.unit
def test_pick_for_portal_skips_quarantined(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    future = int(time.time()) + 3600
    conn.execute(
        "UPDATE identities SET status='active', warming_done=1, quarantine_until=? WHERE id=?",
        (future, idy.id),
    )
    # Active but still inside quarantine window -> not selectable.
    assert store.pick_for_portal(conn, "DE", "autoscout24.de") is None


@pytest.mark.unit
def test_premium_count(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    assert store.premium_count(conn, "DE") == 0
    conn.execute(
        "UPDATE identities SET status='active', trust_score=7.5 WHERE id=?", (idy.id,)
    )
    assert store.premium_count(conn, "DE") == 1
    assert store.premium_count(conn) == 1
    assert store.premium_count(conn, "FR") == 0


@pytest.mark.unit
def test_list_by_status(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    new_ones = store.list_by_status(conn, IdentityStatus.NEW)
    assert len(new_ones) == 1
    assert new_ones[0].id == idy.id
    assert store.list_by_status(conn, IdentityStatus.ACTIVE) == []
