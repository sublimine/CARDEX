-- =============================================================================
-- Migration 002: Portal Cadence — Adaptive scheduling state (§C1)
--
-- Tracks per-portal scrape cadence: current interval, last change detection,
-- and next scheduled scrape. Consumed by the scheduler's DueSource to decide
-- which portals are due. Updated by the writeback layer after each plan_cycle.
--
-- Separate from vehicle_index (indexer domain) and work_queue (SQLite domain).
-- This table is the PG-side §C1 state that the scheduler doc explicitly
-- defers to "the production reader/writeback layer."
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS portal_cadence (
    portal              TEXT NOT NULL,
    country             CHAR(2) NOT NULL,
    current_interval_h  DOUBLE PRECISION NOT NULL DEFAULT 24.0,
    last_change_at      TIMESTAMPTZ,
    last_scrape_at      TIMESTAMPTZ,
    next_scrape_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    listings_last_cycle INT DEFAULT 0,
    listings_delta      INT DEFAULT 0,       -- new - gone from last delta
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (portal, country)
);

CREATE INDEX IF NOT EXISTS idx_portal_cadence_due
    ON portal_cadence (next_scrape_at)
    WHERE enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_portal_cadence_country
    ON portal_cadence (country, enabled);

COMMIT;
