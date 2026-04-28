package browser

import (
	"database/sql"
	"fmt"
	"net/url"
	"strings"
	"sync"
	"time"
)

// HostRateLimiter enforces a minimum inter-request gap per host.
// State is persisted in SQLite so it survives service restarts.
//
// Table: browser_rate_limit_state
//
//	host TEXT PRIMARY KEY
//	last_request_at INTEGER   -- Unix nanoseconds of most recent request
//	requests_current_hour INTEGER -- count of requests in current hour window
//	hour_start INTEGER        -- Unix nanoseconds when the current hour started
type HostRateLimiter struct {
	db          *sql.DB
	minInterval time.Duration
	mu          sync.Mutex
}

const createRateLimitTable = `
CREATE TABLE IF NOT EXISTS browser_rate_limit_state (
    host                    TEXT    PRIMARY KEY,
    last_request_at         INTEGER NOT NULL DEFAULT 0,
    requests_current_hour   INTEGER NOT NULL DEFAULT 0,
    hour_start              INTEGER NOT NULL DEFAULT 0
);`

// NewHostRateLimiter creates a HostRateLimiter using the provided SQLite database.
// The table is created if it does not exist.
func NewHostRateLimiter(db *sql.DB, minInterval time.Duration) (*HostRateLimiter, error) {
	if _, err := db.Exec(createRateLimitTable); err != nil {
		return nil, fmt.Errorf("ratelimit: create table: %w", err)
	}
	return &HostRateLimiter{
		db:          db,
		minInterval: minInterval,
	}, nil
}

// Wait blocks until the minimum interval since the last request to host has
// elapsed. It then records the new request timestamp atomically.
// Callers must call Wait before each page navigation.
func (r *HostRateLimiter) Wait(host string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	now := time.Now()
	last, err := r.lastRequestAt(host)
	if err != nil {
		return fmt.Errorf("ratelimit.Wait: load state: %w", err)
	}

	if elapsed := now.Sub(last); elapsed < r.minInterval {
		sleep := r.minInterval - elapsed
		time.Sleep(sleep)
	}

	return r.recordRequest(host, time.Now())
}

// lastRequestAt returns the timestamp of the most recent request to host, or
// the zero time if no request has been recorded.
func (r *HostRateLimiter) lastRequestAt(host string) (time.Time, error) {
	var nanos int64
	err := r.db.QueryRow(
		`SELECT last_request_at FROM browser_rate_limit_state WHERE host = ?`, host,
	).Scan(&nanos)
	if err == sql.ErrNoRows {
		return time.Time{}, nil
	}
	if err != nil {
		return time.Time{}, fmt.Errorf("ratelimit: query: %w", err)
	}
	if nanos == 0 {
		return time.Time{}, nil
	}
	return time.Unix(0, nanos), nil
}

// recordRequest upserts the request timestamp and increments the hourly counter.
func (r *HostRateLimiter) recordRequest(host string, now time.Time) error {
	nowNano := now.UnixNano()
	hourStart := now.Truncate(time.Hour).UnixNano()

	_, err := r.db.Exec(`
INSERT INTO browser_rate_limit_state (host, last_request_at, requests_current_hour, hour_start)
VALUES (?, ?, 1, ?)
ON CONFLICT(host) DO UPDATE SET
    last_request_at = excluded.last_request_at,
    requests_current_hour = CASE
        WHEN hour_start = excluded.hour_start THEN requests_current_hour + 1
        ELSE 1
    END,
    hour_start = excluded.hour_start
`, host, nowNano, hourStart)
	if err != nil {
		return fmt.Errorf("ratelimit: upsert: %w", err)
	}
	return nil
}

// ExtractHost extracts the lowercase hostname from a URL string.
// Returns the full URL string (for logging) if parsing fails.
func ExtractHost(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		// Fallback: return up to first slash after scheme
		return strings.TrimPrefix(rawURL, "https://")
	}
	return strings.ToLower(u.Hostname())
}
