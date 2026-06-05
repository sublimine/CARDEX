-- 001_arbitrage_alerts.sql
-- Arbitrage alert definitions for the Cross-Border Price Intelligence API.
--
-- The service also applies this schema idempotently at startup
-- (alerts.Store.EnsureSchema); this file is provided for ops that prefer
-- explicit, versioned migrations.
--
-- ADR-0006 (MVCC discipline): alert definitions are immutable once created
-- (INSERT on create, DELETE on remove). Volatile notification state
-- (last signature, last fired time) is kept in Redis, not in mutable columns.

CREATE TABLE IF NOT EXISTS arbitrage_alerts (
    id              TEXT PRIMARY KEY,
    owner           TEXT NOT NULL,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    year_min        INT NOT NULL DEFAULT 0,
    year_max        INT NOT NULL DEFAULT 0,
    fuel            TEXT NOT NULL DEFAULT '',
    mileage_min     INT NOT NULL DEFAULT 0,
    mileage_max     INT NOT NULL DEFAULT 0,
    buy_countries   TEXT[] NOT NULL DEFAULT '{}',
    sell_countries  TEXT[] NOT NULL DEFAULT '{}',
    min_margin_pct  DOUBLE PRECISION NOT NULL DEFAULT 5,
    webhook_url     TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_active ON arbitrage_alerts (active) WHERE active;
CREATE INDEX IF NOT EXISTS idx_alerts_owner ON arbitrage_alerts (owner);
