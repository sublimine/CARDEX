"""Proxy block tests — tiers / pool / health / affinity + schema v2."""
from __future__ import annotations

import time

import pytest

from scrapers import db
from scrapers.engine.identity.profile import ProxyTier
from scrapers.engine.proxy import affinity, health, pool, tiers
from scrapers.engine.proxy.pool import Proxy
from scrapers.engine.router.domain_map import Tier


def _make_proxy(
    ip: str = "203.0.113.10",
    tier: ProxyTier = ProxyTier.ISP_STICKY,
    country: str = "DE",
    provider: str = "decodo",
    port: int = 8000,
    username: str = "user",
    password: str = "pass",
) -> Proxy:
    return Proxy(
        ip=ip, port=port, username=username, password=password,
        tier=tier, provider=provider, country=country,
    )


# ── tiers.py ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_required_proxy_tier_maps_portal_to_proxy():
    assert tiers.required_proxy_tier(Tier.T0) is ProxyTier.ISP_STICKY
    assert tiers.required_proxy_tier(Tier.T1) is ProxyTier.ISP_STICKY
    assert tiers.required_proxy_tier(Tier.T2) is ProxyTier.ISP_STICKY
    assert tiers.required_proxy_tier(Tier.T3) is ProxyTier.RESIDENTIAL_ROTATING


@pytest.mark.unit
def test_provider_for_country_and_tier():
    assert tiers.provider_for(ProxyTier.RESIDENTIAL_ROTATING, "FR") == "bright_data"
    assert tiers.provider_for(ProxyTier.RESIDENTIAL_ROTATING, "DE") == "oxylabs"
    assert tiers.provider_for(ProxyTier.MOBILE, "DE") == "decodo_mobile"
    assert tiers.provider_for(ProxyTier.ISP_STICKY, "DE") == "decodo"


# ── schema v2 ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_schema_version_is_two():
    assert db.SCHEMA_VERSION == 2


@pytest.mark.unit
def test_proxy_affinity_table_exists(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    assert "proxy_affinity" in {r["name"] for r in rows}


@pytest.mark.unit
def test_proxy_health_has_credential_columns(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(proxy_health)")}
    assert {"port", "username", "password"} <= cols


@pytest.mark.unit
def test_ensure_columns_upgrades_existing_v1_table():
    # Simulate a pre-v2 db: a proxy_health WITHOUT the credential columns at v1.
    c = db.connect(":memory:")
    c.execute(
        "CREATE TABLE proxy_health (proxy_ip TEXT PRIMARY KEY, tier TEXT NOT NULL, "
        "provider TEXT NOT NULL, country CHAR(2) NOT NULL, "
        "success_rate REAL NOT NULL DEFAULT 1.0, request_count INTEGER DEFAULT 0, "
        "fail_count INTEGER DEFAULT 0, ban_count_24h INTEGER DEFAULT 0, "
        "status TEXT DEFAULT 'active', quarantine_until INTEGER, "
        "last_ban_at INTEGER, last_success_at INTEGER)"
    )
    c.execute("PRAGMA user_version=1")
    db.migrate(c)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(proxy_health)")}
    assert {"port", "username", "password"} <= cols
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    c.close()


# ── pool.py ───────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_proxy_url_and_playwright_dict():
    p = _make_proxy(ip="1.2.3.4", port=7000, username="u", password="p")
    assert p.url == "http://u:p@1.2.3.4:7000"
    assert p.playwright_dict == {
        "server": "http://1.2.3.4:7000", "username": "u", "password": "p",
    }


@pytest.mark.unit
def test_register_then_pick_roundtrip_with_credentials(conn):
    pool.register(conn, _make_proxy(ip="9.9.9.9", port=1234, username="alice",
                                    password="secret"))
    got = pool.pick(conn, ProxyTier.ISP_STICKY, "DE", "autoscout24.de")
    assert got is not None
    assert got.ip == "9.9.9.9"
    assert got.port == 1234
    assert got.url == "http://alice:secret@9.9.9.9:1234"


@pytest.mark.unit
def test_pick_filters_by_tier_and_country(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1", tier=ProxyTier.ISP_STICKY, country="DE"))
    pool.register(conn, _make_proxy(ip="2.2.2.2", tier=ProxyTier.RESIDENTIAL_ROTATING, country="DE"))
    pool.register(conn, _make_proxy(ip="3.3.3.3", tier=ProxyTier.ISP_STICKY, country="FR"))
    got = pool.pick(conn, ProxyTier.ISP_STICKY, "DE", "x")
    assert got is not None and got.ip == "1.1.1.1"
    assert pool.pick(conn, ProxyTier.MOBILE, "DE", "x") is None


@pytest.mark.unit
def test_pick_prefers_higher_success_rate(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    pool.register(conn, _make_proxy(ip="2.2.2.2"))
    conn.execute("UPDATE proxy_health SET success_rate=0.4 WHERE proxy_ip='1.1.1.1'")
    conn.execute("UPDATE proxy_health SET success_rate=0.95 WHERE proxy_ip='2.2.2.2'")
    # 1.1.1.1 is below the quarantine threshold but not quarantined yet, so both
    # are eligible; the healthier one must win the ranking.
    got = pool.pick(conn, ProxyTier.ISP_STICKY, "DE", "x")
    assert got is not None and got.ip == "2.2.2.2"


@pytest.mark.unit
def test_pick_excludes_quarantined_within_window(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    future = int(time.time()) + 3600
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='1.1.1.1'",
        (health.STATUS_QUARANTINE, future),
    )
    assert pool.pick(conn, ProxyTier.ISP_STICKY, "DE", "x") is None


@pytest.mark.unit
def test_pick_includes_quarantined_after_window(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    past = int(time.time()) - 10
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='1.1.1.1'",
        (health.STATUS_QUARANTINE, past),
    )
    got = pool.pick(conn, ProxyTier.ISP_STICKY, "DE", "x")
    assert got is not None and got.ip == "1.1.1.1"


@pytest.mark.unit
def test_register_upsert_preserves_health_metrics(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1", username="old"))
    conn.execute("UPDATE proxy_health SET success_rate=0.55, ban_count_24h=2 WHERE proxy_ip='1.1.1.1'")
    pool.register(conn, _make_proxy(ip="1.1.1.1", username="new"))  # re-seed
    row = conn.execute("SELECT * FROM proxy_health WHERE proxy_ip='1.1.1.1'").fetchone()
    assert row["username"] == "new"          # static fields refreshed
    assert row["success_rate"] == 0.55       # live metrics untouched
    assert row["ban_count_24h"] == 2


@pytest.mark.unit
def test_record_success_raises_success_rate(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    conn.execute("UPDATE proxy_health SET success_rate=0.5 WHERE proxy_ip='1.1.1.1'")
    pool.record_success(conn, "1.1.1.1")
    row = conn.execute("SELECT success_rate, request_count FROM proxy_health WHERE proxy_ip='1.1.1.1'").fetchone()
    assert row["success_rate"] > 0.5
    assert row["request_count"] == 1


@pytest.mark.unit
def test_record_ban_three_times_quarantines(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    for _ in range(3):
        pool.record_ban(conn, "1.1.1.1")
    row = conn.execute("SELECT * FROM proxy_health WHERE proxy_ip='1.1.1.1'").fetchone()
    assert row["ban_count_24h"] == 3
    assert row["status"] == health.STATUS_QUARANTINE
    assert row["quarantine_until"] is not None


@pytest.mark.unit
def test_health_summary_groups_by_tier(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1", tier=ProxyTier.ISP_STICKY))
    pool.register(conn, _make_proxy(ip="2.2.2.2", tier=ProxyTier.ISP_STICKY))
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='2.2.2.2'",
        (health.STATUS_QUARANTINE, int(time.time()) + 3600),
    )
    summary = pool.health_summary(conn)
    assert summary["isp_sticky"]["total"] == 2
    assert summary["isp_sticky"]["available"] == 1


# ── health.py ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_status_for_thresholds():
    now = 1000
    assert health._status_for(0.95, 0, now)[0] == health.STATUS_ACTIVE
    assert health._status_for(0.65, 0, now)[0] == health.STATUS_SOFT_DEGRADED
    assert health._status_for(0.45, 0, now)[0] == health.STATUS_QUARANTINE
    status, until = health._status_for(0.99, 3, now)  # ban threshold wins
    assert status == health.STATUS_QUARANTINE
    assert until == now + health._QUARANTINE_SECONDS


@pytest.mark.unit
def test_record_result_failure_lowers_rate(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    health.record_result(conn, "1.1.1.1", False)
    row = conn.execute("SELECT success_rate, fail_count FROM proxy_health WHERE proxy_ip='1.1.1.1'").fetchone()
    assert row["success_rate"] < 1.0
    assert row["fail_count"] == 1


@pytest.mark.unit
def test_record_result_frozen_while_quarantined(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    future = int(time.time()) + 3600
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='1.1.1.1'",
        (health.STATUS_QUARANTINE, future),
    )
    health.record_result(conn, "1.1.1.1", True)  # stray probe success
    row = conn.execute("SELECT status FROM proxy_health WHERE proxy_ip='1.1.1.1'").fetchone()
    assert row["status"] == health.STATUS_QUARANTINE  # still frozen


@pytest.mark.unit
def test_record_result_unknown_proxy_is_noop(conn):
    health.record_result(conn, "0.0.0.0", True)  # must not raise
    assert conn.execute("SELECT COUNT(*) AS n FROM proxy_health").fetchone()["n"] == 0


@pytest.mark.unit
def test_is_usable_quarantined_within_window_false(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='1.1.1.1'",
        (health.STATUS_QUARANTINE, int(time.time()) + 3600),
    )
    assert health.is_usable(conn, "1.1.1.1") is False


@pytest.mark.unit
def test_is_usable_after_window_true(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='1.1.1.1'",
        (health.STATUS_QUARANTINE, int(time.time()) - 10),
    )
    assert health.is_usable(conn, "1.1.1.1") is True


@pytest.mark.unit
def test_is_usable_premium_excludes_soft_degraded(conn):
    pool.register(conn, _make_proxy(ip="1.1.1.1"))
    conn.execute("UPDATE proxy_health SET success_rate=0.6 WHERE proxy_ip='1.1.1.1'")
    assert health.is_usable(conn, "1.1.1.1", require_premium=False) is True
    assert health.is_usable(conn, "1.1.1.1", require_premium=True) is False


@pytest.mark.unit
def test_is_usable_unknown_proxy_false(conn):
    assert health.is_usable(conn, "0.0.0.0") is False


# ── affinity.py ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_affinity_set_then_get_roundtrip(conn):
    p = _make_proxy(ip="5.5.5.5", port=4321, username="bob", password="pw")
    pool.register(conn, p)
    affinity.set_affine_proxy(conn, "id-1", "autoscout24.de", p)
    got = affinity.get_affine_proxy(conn, "id-1", "autoscout24.de")
    assert got is not None
    assert got.ip == "5.5.5.5"
    assert got.url == "http://bob:pw@5.5.5.5:4321"


@pytest.mark.unit
def test_affinity_get_returns_none_without_record(conn):
    assert affinity.get_affine_proxy(conn, "nobody", "x.com") is None


@pytest.mark.unit
def test_affinity_get_none_when_proxy_quarantined(conn):
    p = _make_proxy(ip="5.5.5.5")
    pool.register(conn, p)
    affinity.set_affine_proxy(conn, "id-1", "d.com", p)
    conn.execute(
        "UPDATE proxy_health SET status=?, quarantine_until=? WHERE proxy_ip='5.5.5.5'",
        (health.STATUS_QUARANTINE, int(time.time()) + 3600),
    )
    assert affinity.get_affine_proxy(conn, "id-1", "d.com") is None


@pytest.mark.unit
def test_affinity_set_upsert_repins(conn):
    p1 = _make_proxy(ip="5.5.5.5")
    p2 = _make_proxy(ip="6.6.6.6")
    pool.register(conn, p1)
    pool.register(conn, p2)
    affinity.set_affine_proxy(conn, "id-1", "d.com", p1)
    affinity.set_affine_proxy(conn, "id-1", "d.com", p2)  # re-pin
    got = affinity.get_affine_proxy(conn, "id-1", "d.com")
    assert got is not None and got.ip == "6.6.6.6"
