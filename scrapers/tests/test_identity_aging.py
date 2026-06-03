"""Identity aging — trust deltas, quarantine release, premium gate."""
from __future__ import annotations

import time

import pytest

from scrapers.engine.identity import aging, store
from scrapers.engine.identity.profile import IdentityStatus


@pytest.mark.unit
def test_record_success_increments_trust(conn, active_identity):
    before = store.get(conn, active_identity.id).trust_score
    aging.record_success(conn, active_identity.id)
    after = store.get(conn, active_identity.id).trust_score
    assert after == pytest.approx(before + 0.05)


@pytest.mark.unit
def test_record_hard_block_increments_ban_count(conn, active_identity):
    aging.record_hard_block(conn, active_identity.id)
    got = store.get(conn, active_identity.id)
    assert got.ban_count == 1
    assert got.trust_score == pytest.approx(1.0 - 3.0)


@pytest.mark.unit
def test_three_hard_blocks_collapse_to_retired(conn, active_identity):
    for _ in range(3):
        aging.record_hard_block(conn, active_identity.id)
    got = store.get(conn, active_identity.id)
    assert got.ban_count == 3
    assert got.status == IdentityStatus.RETIRED  # -8.0 < -5.0


@pytest.mark.unit
def test_release_quarantine_survivor_returns_to_active(conn, active_identity):
    # Soft-block into quarantine, then expire the window.
    aging.record_soft_block(conn, active_identity.id)  # 1.0 - 1.0 = 0.0, not yet < 0
    aging.record_soft_block(conn, active_identity.id)  # 0.0 - 1.0 = -1.0 -> quarantine
    assert store.get(conn, active_identity.id).status == IdentityStatus.QUARANTINE
    conn.execute(
        "UPDATE identities SET quarantine_until=? WHERE id=?", (1, active_identity.id)
    )

    released = aging.release_quarantine(conn)

    got = store.get(conn, active_identity.id)
    assert released == 1
    assert got.status == IdentityStatus.ACTIVE
    assert got.trust_score == 0.0  # neutral baseline on second chance
    assert got.quarantine_until is None


@pytest.mark.unit
def test_release_quarantine_burned_identity_retired(conn, active_identity):
    # Drive ban_count to 3 while keeping it in quarantine (not yet retired by trust):
    conn.execute(
        "UPDATE identities SET status=?, trust_score=-0.5, quarantine_until=?, ban_count=3 "
        "WHERE id=?",
        (IdentityStatus.QUARANTINE.value, 1, active_identity.id),
    )

    released = aging.release_quarantine(conn)

    got = store.get(conn, active_identity.id)
    assert released == 0  # burned ones are not 'released back to active'
    assert got.status == IdentityStatus.RETIRED
    assert got.retire_reason == "ban_threshold"


@pytest.mark.unit
def test_release_quarantine_respects_window(conn, active_identity):
    future = int(time.time()) + 3600
    conn.execute(
        "UPDATE identities SET status=?, trust_score=-0.5, quarantine_until=? WHERE id=?",
        (IdentityStatus.QUARANTINE.value, future, active_identity.id),
    )
    released = aging.release_quarantine(conn)
    assert released == 0  # still inside the 48h window
    assert store.get(conn, active_identity.id).status == IdentityStatus.QUARANTINE


@pytest.mark.unit
def test_is_premium(conn, active_identity):
    import dataclasses

    assert aging.is_premium(active_identity) is False  # trust 1.0 < 7.0
    premium = dataclasses.replace(active_identity, trust_score=7.5)
    assert aging.is_premium(premium) is True
    inactive = dataclasses.replace(premium, status=IdentityStatus.QUARANTINE)
    assert aging.is_premium(inactive) is False
