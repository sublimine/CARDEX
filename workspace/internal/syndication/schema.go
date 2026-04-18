package syndication

import "database/sql"

const syndicationSchema = `
CREATE TABLE IF NOT EXISTS crm_syndication (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    external_id     TEXT,
    external_url    TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMP,
    published_at    TIMESTAMP,
    withdrawn_at    TIMESTAMP,
    last_synced_at  TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_syndication_vehicle  ON crm_syndication(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_syndication_platform ON crm_syndication(platform);
CREATE INDEX IF NOT EXISTS idx_syndication_status   ON crm_syndication(status);
CREATE INDEX IF NOT EXISTS idx_syndication_retry    ON crm_syndication(next_retry_at)
    WHERE status = 'error';

CREATE TABLE IF NOT EXISTS crm_syndication_activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id  TEXT    NOT NULL,
    platform    TEXT    NOT NULL,
    event       TEXT    NOT NULL,
    detail      TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_syndication_activity_vehicle ON crm_syndication_activity(vehicle_id);
`

// EnsureSchema creates syndication tables if they do not exist.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(syndicationSchema)
	return err
}
