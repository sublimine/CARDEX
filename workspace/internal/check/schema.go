package check

import "database/sql"

const checkSchema = `

-- ── Vehicle identity ──────────────────────────────────────────────────────────
-- One row per unique vehicle (keyed by VIN when available, else country+plate).
-- Updated on each lookup; never deleted.
CREATE TABLE IF NOT EXISTS vehicle_identity (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    vin          TEXT,                          -- ISO 3779 VIN (may be NULL/partial)
    plate        TEXT,
    country      TEXT NOT NULL,
    make         TEXT,
    model        TEXT,
    year         INTEGER,
    fuel_type    TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE (vin) ON CONFLICT REPLACE,
    UNIQUE (country, plate) ON CONFLICT IGNORE
);
CREATE INDEX IF NOT EXISTS idx_vi_vin     ON vehicle_identity(vin);
CREATE INDEX IF NOT EXISTS idx_vi_plate   ON vehicle_identity(country, plate);

-- ── Vehicle events ────────────────────────────────────────────────────────────
-- Append-only log of everything that happens to a vehicle.
-- event_type values:
--   inspection_pass / inspection_fail / inspection_pending  → APK/ITV/CT/TÜV
--   mileage_record        → km reading from any authoritative source
--   registration          → first registration in a country
--   transfer              → change of ownership
--   listing_start         → appeared in a dealer listing
--   listing_end           → removed from dealer listing (sold/expired)
--   price_change          → price updated on a listing
--   embargo_flag          → legal embargo recorded
--   recall_open           → open recall from EU Safety Gate or manufacturer
--   recall_closed         → recall resolved
--   stolen_flag           → reported stolen
--   export_flag           → marked as exported
CREATE TABLE IF NOT EXISTS vehicle_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicle_identity(id),
    event_type   TEXT NOT NULL,
    event_date   TEXT NOT NULL,               -- ISO 8601, best-known date for this event
    recorded_at  TEXT NOT NULL,               -- when CARDEX recorded it
    mileage_km   INTEGER,
    price_eur    REAL,
    source       TEXT NOT NULL,               -- 'rdw'|'dgt'|'cm'|'listing'|'rapex'|'ncap'|...
    source_url   TEXT,
    data_json    TEXT                         -- raw extra fields as JSON
);
CREATE INDEX IF NOT EXISTS idx_ve_vehicle  ON vehicle_events(vehicle_id, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_ve_type     ON vehicle_events(event_type, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_ve_recorded ON vehicle_events(recorded_at DESC);

-- ── Check cache ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS check_cache (
    vin          TEXT PRIMARY KEY,
    report_json  BLOB NOT NULL,
    vin_info_json BLOB,
    fetched_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_check_cache_expires ON check_cache(expires_at);

CREATE TABLE IF NOT EXISTS check_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    vin          TEXT NOT NULL,
    ip           TEXT,
    tenant_id    TEXT,
    requested_at TEXT NOT NULL,
    cache_hit    BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_check_requests_vin ON check_requests(vin);
CREATE INDEX IF NOT EXISTS idx_check_requests_ip  ON check_requests(ip, requested_at);

CREATE TABLE IF NOT EXISTS plate_cache (
    country      TEXT NOT NULL,
    plate        TEXT NOT NULL,
    result_json  BLOB NOT NULL,
    full         INTEGER NOT NULL DEFAULT 0, -- 1 when primary source succeeded (rich data)
    fetched_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    PRIMARY KEY (country, plate)
);
CREATE INDEX IF NOT EXISTS idx_plate_cache_expires ON plate_cache(expires_at);
`

// EnsureSchema creates the check_cache and check_requests tables if absent.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(checkSchema)
	return err
}
