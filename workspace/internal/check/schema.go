package check

import "database/sql"

const checkSchema = `
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
`

// EnsureSchema creates the check_cache and check_requests tables if absent.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(checkSchema)
	return err
}
