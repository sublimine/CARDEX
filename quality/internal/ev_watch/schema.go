// Package ev_watch detects battery-anomaly signals in EV listings by computing
// cohort-normalised price z-scores as a proxy for State-of-Health (SoH).
//
// Data source: vehicle_record JOIN dealer_entity (shared SQLite KG).
// Output: ev_anomaly_scores table — queried by HTTP handlers and CLI.
package ev_watch

import "database/sql"

const anomalySchema = `
CREATE TABLE IF NOT EXISTS ev_anomaly_scores (
    id                 INTEGER  PRIMARY KEY AUTOINCREMENT,
    vehicle_id         TEXT     NOT NULL,
    vin                TEXT,
    make               TEXT     NOT NULL,
    model              TEXT     NOT NULL,
    year               INTEGER  NOT NULL,
    country            TEXT     NOT NULL,
    price_cents        INTEGER  NOT NULL,
    mileage_km         INTEGER  NOT NULL,
    cohort_size        INTEGER  NOT NULL,
    cohort_mean_price  INTEGER  NOT NULL,
    cohort_std_dev     REAL     NOT NULL,
    z_score            REAL     NOT NULL,
    anomaly_flag       BOOLEAN  NOT NULL DEFAULT 0,
    confidence         REAL     NOT NULL,
    estimated_soh      TEXT     NOT NULL,
    detected_at        TIMESTAMP NOT NULL,
    UNIQUE(vehicle_id)
);
CREATE INDEX IF NOT EXISTS idx_ev_anomaly_make    ON ev_anomaly_scores(make);
CREATE INDEX IF NOT EXISTS idx_ev_anomaly_country ON ev_anomaly_scores(country);
CREATE INDEX IF NOT EXISTS idx_ev_anomaly_flag    ON ev_anomaly_scores(anomaly_flag);
CREATE INDEX IF NOT EXISTS idx_ev_anomaly_zscore  ON ev_anomaly_scores(z_score);
`

// EnsureSchema creates the ev_anomaly_scores table idempotently.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(anomalySchema)
	return err
}
