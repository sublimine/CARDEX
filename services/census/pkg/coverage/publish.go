package coverage

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// CoverageEntry is the JSON payload published to Redis for frontier consumption.
type CoverageEntry struct {
	FleetCount      int64   `json:"fleet"`
	ExpectedForSale int     `json:"expected"`
	ObservedCount   int     `json:"observed"`
	Coverage        float64 `json:"coverage"`
	EconomicValue   float64 `json:"econ_value"`
	MedianPrice     float64 `json:"median_price"`
}

// PublishToRedis reads the latest coverage_matrix and publishes each cell to Redis
// as a hash entry for the frontier service to consume.
//
// Key pattern: census:coverage:{country}:{make}:{year}
// Value: JSON CoverageEntry
// TTL: 24h
func PublishToRedis(ctx context.Context, pg *pgxpool.Pool, rdb *redis.Client) error {
	slog.Info("coverage: publishing to Redis")
	start := time.Now()

	rows, err := pg.Query(ctx, `
		SELECT DISTINCT ON (country, make, year)
			country, make, year,
			fleet_count, expected_for_sale, observed_count,
			coverage, economic_value_eur, median_price_eur
		FROM coverage_matrix
		ORDER BY country, make, year, computed_at DESC
	`)
	if err != nil {
		return fmt.Errorf("coverage: query: %w", err)
	}
	defer rows.Close()

	pipe := rdb.Pipeline()
	count := 0

	for rows.Next() {
		var country, make_ string
		var year int
		var entry CoverageEntry

		if err := rows.Scan(
			&country, &make_, &year,
			&entry.FleetCount, &entry.ExpectedForSale, &entry.ObservedCount,
			&entry.Coverage, &entry.EconomicValue, &entry.MedianPrice,
		); err != nil {
			slog.Warn("coverage: scan error", "error", err)
			continue
		}

		key := fmt.Sprintf("census:coverage:%s:%s:%d", country, make_, year)
		data, _ := json.Marshal(entry)
		pipe.Set(ctx, key, data, 24*time.Hour)
		count++

		// Flush pipeline every 1000 entries to avoid memory buildup
		if count%1000 == 0 {
			if _, err := pipe.Exec(ctx); err != nil {
				slog.Warn("coverage: redis pipeline flush error", "error", err)
			}
			pipe = rdb.Pipeline()
		}
	}

	if err := rows.Err(); err != nil {
		return fmt.Errorf("coverage: rows: %w", err)
	}

	// Final flush
	if _, err := pipe.Exec(ctx); err != nil {
		return fmt.Errorf("coverage: redis final flush: %w", err)
	}

	slog.Info("coverage: published to Redis",
		"entries", count,
		"duration_ms", time.Since(start).Milliseconds(),
	)
	return nil
}
