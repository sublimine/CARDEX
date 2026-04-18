package syndication

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"time"
)

const (
	StatusPublished = "published"
	StatusWithdrawn = "withdrawn"
	StatusError     = "error"
	StatusPending   = "pending"
	StatusSkipped   = "skipped"

	maxRetries = 3
)

// SyndicationEngine orchestrates publish/withdraw/sync across all platforms.
type SyndicationEngine struct {
	platforms map[string]Platform
	db        *sql.DB
	log       *slog.Logger
}

// NewEngine returns a SyndicationEngine using the globally registered platforms.
func NewEngine(db *sql.DB, log *slog.Logger) (*SyndicationEngine, error) {
	if err := EnsureSchema(db); err != nil {
		return nil, fmt.Errorf("syndication schema: %w", err)
	}
	return &SyndicationEngine{
		platforms: Registered(),
		db:        db,
		log:       log,
	}, nil
}

// NewEngineWithPlatforms returns an engine using an explicit platform map (useful for tests).
func NewEngineWithPlatforms(db *sql.DB, log *slog.Logger, platforms map[string]Platform) (*SyndicationEngine, error) {
	if err := EnsureSchema(db); err != nil {
		return nil, fmt.Errorf("syndication schema: %w", err)
	}
	return &SyndicationEngine{
		platforms: platforms,
		db:        db,
		log:       log,
	}, nil
}

// PublishVehicle publishes a listing to the requested platforms (or all if empty).
// Returns one SyndicationResult per platform attempted.
func (e *SyndicationEngine) PublishVehicle(
	ctx context.Context,
	vehicleID string,
	listing PlatformListing,
	platformNames []string,
) ([]SyndicationResult, error) {
	targets := e.resolvePlatforms(platformNames)
	var results []SyndicationResult

	for name, p := range targets {
		start := time.Now()
		extID, extURL, err := p.Publish(ctx, listing)
		metricLatency.WithLabelValues(name).Observe(time.Since(start).Seconds())

		result := SyndicationResult{Platform: name}
		if err != nil {
			result.Status = StatusError
			result.Error = err
			metricErrorsTotal.WithLabelValues(name, "publish_failed").Inc()
			metricPublishedTotal.WithLabelValues(name, StatusError).Inc()
			e.upsertRecord(vehicleID, name, "", "", StatusError, err.Error(), false)
			e.logActivity(vehicleID, name, "publish_error", err.Error())
		} else {
			result.Status = StatusPublished
			result.ExternalID = extID
			result.ExternalURL = extURL
			metricPublishedTotal.WithLabelValues(name, StatusPublished).Inc()
			metricActiveListings.WithLabelValues(name).Inc()
			e.upsertRecord(vehicleID, name, extID, extURL, StatusPublished, "", false)
			e.logActivity(vehicleID, name, "published", extURL)
			e.log.Info("syndication published",
				"vehicle_id", vehicleID,
				"platform", name,
				"external_id", extID,
			)
		}
		results = append(results, result)
	}
	return results, nil
}

// WithdrawVehicle removes a listing from all platforms it was published to.
// This is called automatically when a vehicle transitions to sold/reserved.
func (e *SyndicationEngine) WithdrawVehicle(ctx context.Context, vehicleID string) error {
	rows, err := e.db.QueryContext(ctx, `
		SELECT platform, external_id
		FROM crm_syndication
		WHERE vehicle_id = ? AND status = 'published'`, vehicleID)
	if err != nil {
		return fmt.Errorf("withdraw query: %w", err)
	}
	defer rows.Close()

	type rec struct{ platform, extID string }
	var records []rec
	for rows.Next() {
		var r rec
		if err := rows.Scan(&r.platform, &r.extID); err != nil {
			return err
		}
		records = append(records, r)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, r := range records {
		p, ok := e.platforms[r.platform]
		if !ok {
			continue
		}
		start := time.Now()
		werr := p.Withdraw(ctx, r.extID)
		metricLatency.WithLabelValues(r.platform).Observe(time.Since(start).Seconds())

		if werr != nil {
			metricErrorsTotal.WithLabelValues(r.platform, "withdraw_failed").Inc()
			e.log.Warn("syndication withdraw error",
				"vehicle_id", vehicleID,
				"platform", r.platform,
				"err", werr,
			)
		} else {
			metricActiveListings.WithLabelValues(r.platform).Dec()
		}
		e.updateStatus(vehicleID, r.platform, StatusWithdrawn, "")
		e.logActivity(vehicleID, r.platform, "syndication_withdrawn", "vehicle sold/reserved")
	}
	return nil
}

// SyncAll refreshes the status of all active publications from each platform.
func (e *SyndicationEngine) SyncAll(ctx context.Context) error {
	rows, err := e.db.QueryContext(ctx, `
		SELECT vehicle_id, platform, external_id
		FROM crm_syndication
		WHERE status = 'published'`)
	if err != nil {
		return fmt.Errorf("sync_all query: %w", err)
	}
	defer rows.Close()

	type rec struct{ vehicleID, platform, extID string }
	var records []rec
	for rows.Next() {
		var r rec
		if err := rows.Scan(&r.vehicleID, &r.platform, &r.extID); err != nil {
			return err
		}
		records = append(records, r)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, r := range records {
		if ctx.Err() != nil {
			break
		}
		p, ok := e.platforms[r.platform]
		if !ok {
			continue
		}
		status, err := p.Status(ctx, r.extID)
		if err != nil {
			metricErrorsTotal.WithLabelValues(r.platform, "status_check_failed").Inc()
			continue
		}
		if status.State == "withdrawn" || status.State == "expired" {
			e.updateStatus(r.vehicleID, r.platform, StatusWithdrawn, "")
			metricActiveListings.WithLabelValues(r.platform).Dec()
		}
		_, _ = e.db.ExecContext(ctx, `
			UPDATE crm_syndication SET last_synced_at = CURRENT_TIMESTAMP
			WHERE vehicle_id = ? AND platform = ?`, r.vehicleID, r.platform)
	}
	return nil
}

// RetryErrors retries failed syndication records with exponential backoff.
// Max retries = 3; backoff: 1h → 2h → 4h.
func (e *SyndicationEngine) RetryErrors(ctx context.Context, getListing func(vehicleID string) (PlatformListing, error)) error {
	rows, err := e.db.QueryContext(ctx, `
		SELECT vehicle_id, platform, retry_count
		FROM crm_syndication
		WHERE status = 'error'
		  AND retry_count < ?
		  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
		ORDER BY next_retry_at ASC
		LIMIT 50`, maxRetries)
	if err != nil {
		return fmt.Errorf("retry query: %w", err)
	}
	defer rows.Close()

	type rec struct {
		vehicleID, platform string
		retryCount          int
	}
	var records []rec
	for rows.Next() {
		var r rec
		if err := rows.Scan(&r.vehicleID, &r.platform, &r.retryCount); err != nil {
			return err
		}
		records = append(records, r)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, r := range records {
		if ctx.Err() != nil {
			break
		}
		p, ok := e.platforms[r.platform]
		if !ok {
			continue
		}
		listing, err := getListing(r.vehicleID)
		if err != nil {
			e.log.Warn("retry: cannot load listing", "vehicle_id", r.vehicleID, "err", err)
			continue
		}

		start := time.Now()
		extID, extURL, pubErr := p.Publish(ctx, listing)
		metricLatency.WithLabelValues(r.platform).Observe(time.Since(start).Seconds())

		newRetryCount := r.retryCount + 1
		if pubErr != nil {
			backoff := time.Duration(1<<uint(r.retryCount)) * time.Hour
			nextRetry := time.Now().Add(backoff)
			_, _ = e.db.ExecContext(ctx, `
				UPDATE crm_syndication
				SET error_message = ?, retry_count = ?, next_retry_at = ?, updated_at = CURRENT_TIMESTAMP
				WHERE vehicle_id = ? AND platform = ?`,
				pubErr.Error(), newRetryCount, nextRetry.UTC().Format(time.RFC3339),
				r.vehicleID, r.platform)
			metricErrorsTotal.WithLabelValues(r.platform, "retry_failed").Inc()
		} else {
			e.upsertRecord(r.vehicleID, r.platform, extID, extURL, StatusPublished, "", false)
			metricPublishedTotal.WithLabelValues(r.platform, StatusPublished).Inc()
			metricActiveListings.WithLabelValues(r.platform).Inc()
			e.logActivity(r.vehicleID, r.platform, "retry_published", extURL)
		}
	}
	return nil
}

// ── DB helpers ────────────────────────────────────────────────────────────────

func (e *SyndicationEngine) upsertRecord(vehicleID, platform, extID, extURL, status, errMsg string, setNextRetry bool) {
	now := time.Now().UTC().Format(time.RFC3339)
	var publishedAt, withdrawnAt interface{}
	if status == StatusPublished {
		publishedAt = now
	}
	if status == StatusWithdrawn {
		withdrawnAt = now
	}
	nextRetry := interface{}(nil)
	if setNextRetry {
		nextRetry = time.Now().Add(1 * time.Hour).UTC().Format(time.RFC3339)
	}
	_, _ = e.db.Exec(`
		INSERT INTO crm_syndication
			(vehicle_id, platform, external_id, external_url, status, error_message,
			 retry_count, next_retry_at, published_at, withdrawn_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, CURRENT_TIMESTAMP)
		ON CONFLICT(vehicle_id, platform) DO UPDATE SET
			external_id    = excluded.external_id,
			external_url   = excluded.external_url,
			status         = excluded.status,
			error_message  = excluded.error_message,
			next_retry_at  = excluded.next_retry_at,
			published_at   = COALESCE(excluded.published_at, crm_syndication.published_at),
			withdrawn_at   = excluded.withdrawn_at,
			updated_at     = CURRENT_TIMESTAMP`,
		vehicleID, platform, extID, extURL, status, errMsg,
		nextRetry, publishedAt, withdrawnAt)
}

func (e *SyndicationEngine) updateStatus(vehicleID, platform, status, errMsg string) {
	_, _ = e.db.Exec(`
		UPDATE crm_syndication
		SET status = ?, error_message = ?, withdrawn_at = CASE WHEN ? = 'withdrawn' THEN CURRENT_TIMESTAMP ELSE withdrawn_at END,
		    updated_at = CURRENT_TIMESTAMP
		WHERE vehicle_id = ? AND platform = ?`,
		status, errMsg, status, vehicleID, platform)
}

func (e *SyndicationEngine) logActivity(vehicleID, platform, event, detail string) {
	_, _ = e.db.Exec(`
		INSERT INTO crm_syndication_activity (vehicle_id, platform, event, detail)
		VALUES (?, ?, ?, ?)`,
		vehicleID, platform, event, detail)
}

// resolvePlatforms returns the target platforms for an operation.
// If names is empty, all registered platforms are returned.
func (e *SyndicationEngine) resolvePlatforms(names []string) map[string]Platform {
	if len(names) == 0 {
		return e.platforms
	}
	out := make(map[string]Platform, len(names))
	for _, n := range names {
		if p, ok := e.platforms[n]; ok {
			out[n] = p
		}
	}
	return out
}
