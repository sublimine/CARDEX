"""Foundation tests — engine.db WAL factory + idempotent migrations."""
from __future__ import annotations

import pytest

from scrapers import db

_EXPECTED_TABLES = {
    "identities",
    "domain_tier_state",
    "proxy_health",
    "work_queue",
    "dlq",
    "schema_registry",
    "warming_schedule",
}


@pytest.mark.unit
def test_migrate_creates_all_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert _EXPECTED_TABLES <= names


@pytest.mark.unit
def test_migrate_sets_schema_version(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == db.SCHEMA_VERSION


@pytest.mark.unit
def test_migrate_is_idempotent(conn):
    # Second migrate on an already-current db must be a no-op, not raise.
    db.migrate(conn)
    db.migrate(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == db.SCHEMA_VERSION


@pytest.mark.unit
def test_row_factory_allows_name_access(conn):
    conn.execute(
        "INSERT INTO proxy_health (proxy_ip, tier, provider, country) "
        "VALUES ('1.2.3.4', 'isp_sticky', 'decodo', 'DE')"
    )
    row = conn.execute(
        "SELECT proxy_ip, country FROM proxy_health WHERE proxy_ip='1.2.3.4'"
    ).fetchone()
    assert row["proxy_ip"] == "1.2.3.4"
    assert row["country"] == "DE"


@pytest.mark.unit
def test_identities_primary_key_is_unique(conn):
    import sqlite3

    conn.execute(
        "INSERT INTO identities (id, country, proxy_ip, proxy_tier, proxy_provider, "
        "tcp_profile, tls_profile, fingerprint, created_at) "
        "VALUES ('x', 'DE', '1.1.1.1', 'isp_sticky', 'decodo', "
        "'windows_11', 'chrome136', 'null', 0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO identities (id, country, proxy_ip, proxy_tier, proxy_provider, "
            "tcp_profile, tls_profile, fingerprint, created_at) "
            "VALUES ('x', 'FR', '2.2.2.2', 'mobile', 'oxylabs', "
            "'macos_14', 'safari260', 'null', 0)"
        )
