package pulse

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
)

// EnsureTable creates the dealer_health_history table if it does not exist.
func EnsureTable(ctx context.Context, db *sql.DB) error {
	_, err := db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS dealer_health_history (
		  id           INTEGER PRIMARY KEY AUTOINCREMENT,
		  dealer_id    TEXT    NOT NULL REFERENCES dealer_entity(dealer_id),
		  health_score REAL    NOT NULL,
		  health_tier  TEXT    NOT NULL,
		  signals_json TEXT    NOT NULL,
		  computed_at  TEXT    NOT NULL
		);
		CREATE INDEX IF NOT EXISTS idx_dhh_dealer_time
		  ON dealer_health_history(dealer_id, computed_at);
	`)
	if err != nil {
		return fmt.Errorf("pulse.storage: ensure table: %w", err)
	}
	return nil
}

// SaveSnapshot persists a DealerHealthScore to dealer_health_history.
func SaveSnapshot(ctx context.Context, db *sql.DB, s *DealerHealthScore) error {
	signalsJSON, err := json.Marshal(s.RiskSignals)
	if err != nil {
		return fmt.Errorf("pulse.storage: marshal signals: %w", err)
	}
	_, err = db.ExecContext(ctx, `
		INSERT INTO dealer_health_history
		  (dealer_id, health_score, health_tier, signals_json, computed_at)
		VALUES (?, ?, ?, ?, ?)`,
		s.DealerID,
		s.HealthScore,
		s.HealthTier,
		string(signalsJSON),
		s.ComputedAt.UTC().Format(time.RFC3339),
	)
	if err != nil {
		return fmt.Errorf("pulse.storage: save snapshot: %w", err)
	}
	return nil
}

// LoadHistory returns historical snapshots for dealerID ordered oldest-first.
// limit controls the maximum number of rows returned (0 = all).
func LoadHistory(ctx context.Context, db *sql.DB, dealerID string, limit int) ([]HistoryPoint, error) {
	query := `
		SELECT dealer_id, health_score, health_tier, signals_json, computed_at
		FROM dealer_health_history
		WHERE dealer_id = ?
		ORDER BY computed_at ASC`
	if limit > 0 {
		query += fmt.Sprintf(" LIMIT %d", limit)
	}

	rows, err := db.QueryContext(ctx, query, dealerID)
	if err != nil {
		return nil, fmt.Errorf("pulse.storage: load history: %w", err)
	}
	defer rows.Close()

	var out []HistoryPoint
	for rows.Next() {
		var h HistoryPoint
		var computedAt string
		if err := rows.Scan(&h.DealerID, &h.HealthScore, &h.HealthTier, &h.SignalsJSON, &computedAt); err != nil {
			return nil, fmt.Errorf("pulse.storage: scan history: %w", err)
		}
		h.ComputedAt, _ = time.Parse(time.RFC3339, computedAt)
		out = append(out, h)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pulse.storage: history rows: %w", err)
	}
	return out, nil
}

// Watchlist returns the latest health snapshot for each dealer whose most recent
// score falls below maxScore. Results are ordered by health_score ascending (worst first).
func Watchlist(ctx context.Context, db *sql.DB, maxScore float64, country string) ([]HistoryPoint, error) {
	args := []any{maxScore}
	countryFilter := ""
	if country != "" {
		countryFilter = `AND de.country_code = ?`
		args = append(args, country)
	}

	query := fmt.Sprintf(`
		SELECT h.dealer_id, h.health_score, h.health_tier, h.signals_json, h.computed_at
		FROM dealer_health_history h
		JOIN (
		  SELECT dealer_id, MAX(computed_at) AS latest
		  FROM dealer_health_history
		  GROUP BY dealer_id
		) latest ON h.dealer_id = latest.dealer_id AND h.computed_at = latest.latest
		JOIN dealer_entity de ON h.dealer_id = de.dealer_id
		WHERE h.health_score < ? %s
		ORDER BY h.health_score ASC`, countryFilter)

	rows, err := db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("pulse.storage: watchlist: %w", err)
	}
	defer rows.Close()

	var out []HistoryPoint
	for rows.Next() {
		var h HistoryPoint
		var computedAt string
		if err := rows.Scan(&h.DealerID, &h.HealthScore, &h.HealthTier, &h.SignalsJSON, &computedAt); err != nil {
			return nil, fmt.Errorf("pulse.storage: watchlist scan: %w", err)
		}
		h.ComputedAt, _ = time.Parse(time.RFC3339, computedAt)
		out = append(out, h)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pulse.storage: watchlist rows: %w", err)
	}
	return out, nil
}

// PruneOld deletes history rows older than retainDays days.
func PruneOld(ctx context.Context, db *sql.DB, retainDays int) (int64, error) {
	cutoff := time.Now().UTC().AddDate(0, 0, -retainDays).Format(time.RFC3339)
	res, err := db.ExecContext(ctx,
		`DELETE FROM dealer_health_history WHERE computed_at < ?`, cutoff)
	if err != nil {
		return 0, fmt.Errorf("pulse.storage: prune: %w", err)
	}
	n, _ := res.RowsAffected()
	return n, nil
}
