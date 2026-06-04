"""
engine.db — SQLite WAL factory.

Single source of truth for all scraping state:
  identities, proxy health, domain tier state, work queue, DLQ, schema registry,
  warming schedule.

Schema defined in SCRAPING_ENGINE.md § DATA MODEL. WAL mode: concurrent readers
never block the writer. Migrations are idempotent (guarded by PRAGMA user_version)
so `migrate()` is safe to call on every process startup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent / "engine.db"

# Bump when the DDL below changes in a way that needs a new migration step.
SCHEMA_VERSION = 2

_BUSY_TIMEOUT_MS = 10_000

# Full DDL. Every statement is CREATE ... IF NOT EXISTS so re-running is a no-op.
# `quarantine_until` is added to `identities` beyond the doc's column list because
# aging.release_quarantine() needs the 48h re-evaluation boundary persisted; the
# doc describes the 48h behaviour (§A1 inv.4) without naming the column.
_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS identities (
        id                TEXT PRIMARY KEY,
        country           CHAR(2) NOT NULL,
        status            TEXT NOT NULL DEFAULT 'new',
        proxy_ip          TEXT NOT NULL,
        proxy_tier        TEXT NOT NULL,
        proxy_provider    TEXT NOT NULL,
        tcp_profile       TEXT NOT NULL,
        tls_profile       TEXT NOT NULL,
        fingerprint       TEXT NOT NULL,
        storage_state     BLOB,
        abck_tokens       TEXT NOT NULL DEFAULT '{}',
        browsing_history  TEXT NOT NULL DEFAULT '[]',
        trust_score       REAL NOT NULL DEFAULT 0.0,
        request_count     INTEGER NOT NULL DEFAULT 0,
        ban_count         INTEGER NOT NULL DEFAULT 0,
        warming_done      INTEGER NOT NULL DEFAULT 0,
        warming_started   INTEGER,
        quarantine_until  INTEGER,
        created_at        INTEGER NOT NULL,
        last_used         INTEGER,
        retired_at        INTEGER,
        retire_reason     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_id_country_status "
    "ON identities(country, status, trust_score DESC)",
    """
    CREATE TABLE IF NOT EXISTS domain_tier_state (
        domain            TEXT NOT NULL,
        tier              TEXT NOT NULL,
        waf               TEXT NOT NULL DEFAULT 'unknown',
        circuit_state     TEXT NOT NULL DEFAULT 'closed',
        fail_count        INTEGER NOT NULL DEFAULT 0,
        success_rate      REAL NOT NULL DEFAULT 1.0,
        effective_tier    TEXT,
        opened_at         INTEGER,
        verified_at       INTEGER,
        last_fail         INTEGER,
        last_success      INTEGER,
        PRIMARY KEY (domain, tier)
    )
    """,
    # port/username/password are stored beyond the doc's column list because
    # pool.pick() reconstructs a full Proxy (credentials included) straight from
    # this row — mirroring the identities table, which persists the whole object.
    # DEFAULTs keep older inserts (and test fixtures) that omit them valid.
    """
    CREATE TABLE IF NOT EXISTS proxy_health (
        proxy_ip          TEXT PRIMARY KEY,
        tier              TEXT NOT NULL,
        provider          TEXT NOT NULL,
        country           CHAR(2) NOT NULL,
        port              INTEGER NOT NULL DEFAULT 0,
        username          TEXT NOT NULL DEFAULT '',
        password          TEXT NOT NULL DEFAULT '',
        success_rate      REAL NOT NULL DEFAULT 1.0,
        request_count     INTEGER NOT NULL DEFAULT 0,
        fail_count        INTEGER NOT NULL DEFAULT 0,
        ban_count_24h     INTEGER NOT NULL DEFAULT 0,
        status            TEXT NOT NULL DEFAULT 'active',
        quarantine_until  INTEGER,
        last_ban_at       INTEGER,
        last_success_at   INTEGER
    )
    """,
    # Proxy↔domain affinity: same IP for the same (identity, domain) all session
    # long. Akamai/CF correlate a session by IP, so a mid-session IP change is an
    # instant ban (affinity.py). proxy_ip references a proxy_health row logically;
    # no FK so an evicted proxy_health row never blocks affinity bookkeeping.
    """
    CREATE TABLE IF NOT EXISTS proxy_affinity (
        identity_id       TEXT NOT NULL,
        domain            TEXT NOT NULL,
        proxy_ip          TEXT NOT NULL,
        assigned_at       INTEGER NOT NULL,
        PRIMARY KEY (identity_id, domain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS work_queue (
        id                TEXT PRIMARY KEY,
        portal            TEXT NOT NULL,
        country           CHAR(2) NOT NULL,
        tier              TEXT,
        identity_id       TEXT,
        filter_params     TEXT,
        status            TEXT NOT NULL DEFAULT 'pending',
        priority          INTEGER NOT NULL DEFAULT 5,
        attempts          INTEGER NOT NULL DEFAULT 0,
        last_error        TEXT,
        created_at        INTEGER NOT NULL,
        scheduled_at      INTEGER NOT NULL,
        started_at        INTEGER,
        completed_at      INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_wq_scheduled "
    "ON work_queue(status, scheduled_at)",
    """
    CREATE TABLE IF NOT EXISTS dlq (
        url_hash          TEXT PRIMARY KEY,
        url               TEXT NOT NULL,
        portal            TEXT NOT NULL,
        fail_count        INTEGER NOT NULL DEFAULT 1,
        dlq_reason        TEXT NOT NULL,
        last_error        TEXT,
        first_fail        INTEGER NOT NULL,
        last_fail         INTEGER NOT NULL,
        retry_after       INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dlq_retry ON dlq(retry_after)",
    """
    CREATE TABLE IF NOT EXISTS schema_registry (
        portal            TEXT PRIMARY KEY,
        schema_fp         TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        sample_count      INTEGER NOT NULL DEFAULT 0,
        verified_at       INTEGER NOT NULL,
        last_change_at    INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS warming_schedule (
        identity_id       TEXT NOT NULL,
        target_domain     TEXT NOT NULL,
        phase             INTEGER NOT NULL,
        requests_done     INTEGER NOT NULL DEFAULT 0,
        requests_target   INTEGER NOT NULL,
        started_at        INTEGER,
        completed_at      INTEGER,
        PRIMARY KEY (identity_id, target_domain, phase)
    )
    """,
)


def connect(path: Path | str = _DEFAULT_PATH) -> sqlite3.Connection:
    """
    Return a WAL-mode connection. Thread-local — do not share across threads.

    A path of ":memory:" yields an isolated in-memory database (used by tests).
    Row factory is sqlite3.Row so callers read columns by name.
    """
    conn = sqlite3.connect(
        str(path), timeout=_BUSY_TIMEOUT_MS / 1000, isolation_level=None
    )
    conn.row_factory = sqlite3.Row
    # WAL is a no-op for :memory: databases but harmless to request.
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    return conn


# Columns added to existing tables after their first release. CREATE ... IF NOT
# EXISTS never alters a table that already exists, so an in-place upgrade needs an
# explicit ADD COLUMN. Names come from this constant only — never user input.
_ADDED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "proxy_health": (
        ("port", "INTEGER NOT NULL DEFAULT 0"),
        ("username", "TEXT NOT NULL DEFAULT ''"),
        ("password", "TEXT NOT NULL DEFAULT ''"),
    ),
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add post-release columns to pre-existing tables (idempotent)."""
    for table, columns in _ADDED_COLUMNS.items():
        existing = {
            r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all DDL migrations idempotently. Safe to call on every startup."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current >= SCHEMA_VERSION:
        return
    with conn:  # implicit transaction around the whole migration
        for statement in _DDL:
            conn.execute(statement)
        _ensure_columns(conn)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
