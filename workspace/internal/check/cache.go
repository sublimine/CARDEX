package check

import (
	"context"
	"database/sql"
	"encoding/json"
	"time"
)

const (
	reportTTL  = 24 * time.Hour
	vinInfoTTL = 0 // permanent (VIN decode is immutable)
)

// Cache provides read/write access to the check_cache SQLite table.
type Cache struct {
	db *sql.DB
}

// NewCache wraps the shared database connection.
func NewCache(db *sql.DB) *Cache {
	c := &Cache{db: db}
	go c.cleanupLoop()
	return c
}

// GetReport returns a cached VehicleReport for the given VIN and true,
// or nil and false if no fresh entry exists.
func (c *Cache) GetReport(ctx context.Context, vin string) (*VehicleReport, bool) {
	row := c.db.QueryRowContext(ctx,
		`SELECT report_json FROM check_cache
		 WHERE vin=? AND expires_at > ?`,
		vin, time.Now().UTC().Format(time.RFC3339))
	var blob []byte
	if err := row.Scan(&blob); err != nil {
		return nil, false
	}
	var report VehicleReport
	if err := json.Unmarshal(blob, &report); err != nil {
		return nil, false
	}
	return &report, true
}

// SetReport writes (or replaces) the cached report for a VIN with a 24-hour TTL.
func (c *Cache) SetReport(ctx context.Context, report *VehicleReport) error {
	blob, err := json.Marshal(report)
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	_, err = c.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO check_cache(vin, report_json, fetched_at, expires_at)
		 VALUES(?, ?, ?, ?)`,
		report.VIN, blob,
		now.Format(time.RFC3339),
		now.Add(reportTTL).Format(time.RFC3339),
	)
	return err
}

// RecordRequest inserts an audit row into check_requests.
func (c *Cache) RecordRequest(ctx context.Context, vin, ip, tenantID string, cacheHit bool) {
	_, _ = c.db.ExecContext(ctx,
		`INSERT INTO check_requests(vin, ip, tenant_id, requested_at, cache_hit)
		 VALUES(?, ?, ?, ?, ?)`,
		vin, ip, tenantID, time.Now().UTC().Format(time.RFC3339), cacheHit,
	)
}

func (c *Cache) cleanupLoop() {
	ticker := time.NewTicker(1 * time.Hour)
	for range ticker.C {
		_, _ = c.db.Exec(
			`DELETE FROM check_cache WHERE expires_at <= ?`,
			time.Now().UTC().Format(time.RFC3339),
		)
	}
}
