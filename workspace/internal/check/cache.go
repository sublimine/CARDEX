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

	// plateCacheTTLFull applies when the primary (rich) source succeeded.
	// Vehicle specs don't change, so 30 days is safe and protects us from
	// comprobarmatricula.com rate-limits on repeat lookups.
	plateCacheTTLFull = 30 * 24 * time.Hour
	// plateCacheTTLPartial applies when only a fallback source answered
	// (e.g. ES got only the DGT badge because CM rate-limited us). Short
	// TTL so we retry the primary source soon.
	plateCacheTTLPartial = 1 * time.Hour
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
		now := time.Now().UTC().Format(time.RFC3339)
		_, _ = c.db.Exec(`DELETE FROM check_cache WHERE expires_at <= ?`, now)
		_, _ = c.db.Exec(`DELETE FROM plate_cache WHERE expires_at <= ?`, now)
	}
}

// GetPlate returns a cached PlateResult for (country, plate) if one exists
// and has not expired. full=true means the primary rich source was captured
// (so the cached data is worth surfacing as-is); full=false means the entry
// is a partial fallback worth refreshing when possible.
func (c *Cache) GetPlate(ctx context.Context, country, plate string) (result *PlateResult, full bool, ok bool) {
	if c == nil || c.db == nil {
		return nil, false, false
	}
	row := c.db.QueryRowContext(ctx,
		`SELECT result_json, full FROM plate_cache
		 WHERE country=? AND plate=? AND expires_at > ?`,
		country, plate, time.Now().UTC().Format(time.RFC3339))
	var blob []byte
	var fullInt int
	if err := row.Scan(&blob, &fullInt); err != nil {
		return nil, false, false
	}
	var pr PlateResult
	if err := json.Unmarshal(blob, &pr); err != nil {
		return nil, false, false
	}
	return &pr, fullInt == 1, true
}

// SetPlate stores a PlateResult with the appropriate TTL. full=true applies
// the 30-day TTL; full=false applies the 1-hour partial TTL so the caller
// keeps probing the primary source.
func (c *Cache) SetPlate(ctx context.Context, country, plate string, result *PlateResult, full bool) error {
	if c == nil || c.db == nil || result == nil {
		return nil
	}
	blob, err := json.Marshal(result)
	if err != nil {
		return err
	}
	ttl := plateCacheTTLPartial
	fullInt := 0
	if full {
		ttl = plateCacheTTLFull
		fullInt = 1
	}
	now := time.Now().UTC()
	_, err = c.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO plate_cache(country, plate, result_json, full, fetched_at, expires_at)
		 VALUES(?, ?, ?, ?, ?, ?)`,
		country, plate, blob, fullInt,
		now.Format(time.RFC3339),
		now.Add(ttl).Format(time.RFC3339),
	)
	return err
}
