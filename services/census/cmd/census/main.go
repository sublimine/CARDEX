package main

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/cardex/census/pkg/coverage"
	"github.com/cardex/census/pkg/sources"
)

type Deps struct {
	pg  *pgxpool.Pool
	ch  clickhouse.Conn
	rdb *redis.Client
}

func mustConnect(ctx context.Context) *Deps {
	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@postgres:5432/cardex")
	pg, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("census: postgres connect failed", "error", err)
		os.Exit(1)
	}
	if err = pg.Ping(ctx); err != nil {
		slog.Error("census: postgres ping failed", "error", err)
		os.Exit(1)
	}

	ch, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{envOrDefault("CLICKHOUSE_ADDR", "clickhouse:9000")},
		Auth: clickhouse.Auth{
			Database: "cardex",
			Username: envOrDefault("CLICKHOUSE_USER", "default"),
			Password: envOrDefault("CLICKHOUSE_PASSWORD", ""),
		},
		DialTimeout:     10 * time.Second,
		MaxOpenConns:    4,
		MaxIdleConns:    2,
		ConnMaxLifetime: time.Hour,
	})
	if err != nil {
		slog.Error("census: clickhouse open failed", "error", err)
		os.Exit(1)
	}
	if err = ch.Ping(ctx); err != nil {
		slog.Error("census: clickhouse ping failed", "error", err)
		os.Exit(1)
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:     envOrDefault("REDIS_ADDR", "redis:6379"),
		PoolSize: 10,
	})
	if err = rdb.Ping(ctx).Err(); err != nil {
		slog.Error("census: redis ping failed", "error", err)
		os.Exit(1)
	}

	slog.Info("census: all connections established")
	return &Deps{pg: pg, ch: ch, rdb: rdb}
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	d := mustConnect(ctx)
	defer d.pg.Close()
	defer d.ch.Close()
	defer d.rdb.Close()

	slog.Info("census: service started")

	// Ingest all census sources daily at 04:00 UTC
	go dailyAt(ctx, 4, d.ingestAllSources)

	// Recompute coverage matrix every 6 hours
	go every(ctx, 6*time.Hour, d.recomputeCoverage)

	// Publish coverage to Redis for frontier consumption every 6 hours (offset by 10min)
	go func() {
		time.Sleep(10 * time.Minute) // Wait for first coverage computation
		every(ctx, 6*time.Hour, d.publishCoverage)
	}()

	// Replicate coverage snapshots to ClickHouse daily at 05:00 UTC
	go dailyAt(ctx, 5, d.replicateToClickHouse)

	// Prune old coverage snapshots weekly
	go weeklyOn(ctx, time.Sunday, 3, d.pruneOld)

	<-ctx.Done()
	slog.Info("census: shutting down")
}

// retryWithBackoff retries fn up to maxRetries times with exponential backoff.
// Delays: 1s, 2s, 4s (for maxRetries=3). Adds ±25% jitter to prevent thundering herd.
func retryWithBackoff(ctx context.Context, name string, maxRetries int, fn func() error) error {
	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		lastErr = fn()
		if lastErr == nil {
			return nil
		}
		if attempt < maxRetries {
			base := time.Duration(1<<uint(attempt)) * time.Second // 1s, 2s, 4s
			jitter := time.Duration(float64(base) * (0.75 + 0.5*rand.Float64())) // ±25%
			slog.Warn("census: retry", "source", name, "attempt", attempt+1, "delay", jitter, "error", lastErr)
			select {
			case <-time.After(jitter):
			case <-ctx.Done():
				return ctx.Err()
			}
		}
	}
	return fmt.Errorf("census: %s failed after %d retries: %w", name, maxRetries+1, lastErr)
}

// ingestAllSources fetches registration statistics from all configured government sources
// and upserts them into fleet_census.
func (d *Deps) ingestAllSources(ctx context.Context) {
	slog.Info("census: ingesting all sources")

	rdwToken := envOrDefault("RDW_APP_TOKEN", "")

	allSources := []sources.CensusSource{
		sources.NewKBA(),
		sources.NewRDW(rdwToken),
		sources.NewDGT(),
		sources.NewSDES(),
		sources.NewDIV(),
		sources.NewASTRA(),
	}

	totalIngested := 0

	for _, src := range allSources {
		var records []sources.FleetRecord
		err := retryWithBackoff(ctx, src.ID(), 3, func() error {
			var fetchErr error
			records, fetchErr = src.Fetch(ctx)
			return fetchErr
		})
		if err != nil {
			slog.Error("census: source fetch failed", "source", src.ID(), "error", err)
			continue
		}

		totalCount := len(records)
		ingested, err := d.upsertRecords(ctx, records)
		if err != nil {
			slog.Error("census: upsert failed", "source", src.ID(), "error", err)
			continue
		}

		// B11: Log warning if CSV discard rate exceeds 10%
		discardCount := totalCount - ingested
		if discardCount > 0 && float64(discardCount)/float64(totalCount) > 0.10 {
			slog.Warn("census: high discard rate", "source", src.ID(), "discarded", discardCount, "total", totalCount, "rate", fmt.Sprintf("%.1f%%", float64(discardCount)*100/float64(totalCount)))
		}

		totalIngested += ingested
		slog.Info("census: source ingested", "source", src.ID(), "records", ingested)
	}

	slog.Info("census: all sources ingested", "total", totalIngested)
}

// upsertRecords inserts FleetRecords into fleet_census with ON CONFLICT upsert.
func (d *Deps) upsertRecords(ctx context.Context, records []sources.FleetRecord) (int, error) {
	if len(records) == 0 {
		return 0, nil
	}

	// Batch insert using a transaction
	tx, err := d.pg.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("census: begin tx: %w", err)
	}
	defer tx.Rollback(ctx)

	count := 0
	for _, r := range records {
		_, err := tx.Exec(ctx, `
			INSERT INTO fleet_census (country, make, year, fuel_type, vehicle_count, as_of_date, source, raw_category)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
			ON CONFLICT (country, make, year, fuel_type, source, as_of_date)
			DO UPDATE SET vehicle_count = EXCLUDED.vehicle_count, ingested_at = NOW()
		`, r.Country, r.Make, r.Year, r.FuelType, r.Count, r.AsOfDate, r.Source, r.RawCategory)
		if err != nil {
			slog.Warn("census: upsert row failed", "make", r.Make, "year", r.Year, "error", err)
			continue
		}
		count++
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("census: commit: %w", err)
	}

	return count, nil
}

// recomputeCoverage recalculates the coverage matrix from fleet_census + active listings.
func (d *Deps) recomputeCoverage(ctx context.Context) {
	rows, err := coverage.ComputeMatrix(ctx, d.pg)
	if err != nil {
		slog.Error("census: coverage compute failed", "error", err)
		return
	}
	slog.Info("census: coverage matrix updated", "rows", rows)
}

// publishCoverage pushes coverage data to Redis for the frontier service.
func (d *Deps) publishCoverage(ctx context.Context) {
	if err := coverage.PublishToRedis(ctx, d.pg, d.rdb); err != nil {
		slog.Error("census: coverage publish failed", "error", err)
	}
}

// replicateToClickHouse copies the latest coverage_matrix snapshot to ClickHouse for analytics.
func (d *Deps) replicateToClickHouse(ctx context.Context) {
	slog.Info("census: replicating coverage to ClickHouse")

	rows, err := d.pg.Query(ctx, `
		SELECT DISTINCT ON (country, make, year, fuel_type)
			country, make, year, fuel_type,
			fleet_count, expected_for_sale, observed_count,
			coverage, economic_value_eur, median_price_eur
		FROM coverage_matrix
		ORDER BY country, make, year, fuel_type, computed_at DESC
	`)
	if err != nil {
		slog.Error("census: ch query failed", "error", err)
		return
	}
	defer rows.Close()

	batch, err := d.ch.PrepareBatch(ctx, `
		INSERT INTO cardex.coverage_snapshots (
			snapshot_date, country, make, year, fuel_type,
			fleet_count, expected_for_sale, observed_count,
			coverage, economic_value_eur, median_price_eur
		)
	`)
	if err != nil {
		slog.Error("census: ch prepare batch failed", "error", err)
		return
	}

	today := time.Now().Truncate(24 * time.Hour)
	count := 0

	for rows.Next() {
		var country, make_, fuelType string
		var year int
		var fleetCount int64
		var expectedForSale, observedCount int
		var cov, econValue, medianPrice float64

		if err := rows.Scan(&country, &make_, &year, &fuelType,
			&fleetCount, &expectedForSale, &observedCount,
			&cov, &econValue, &medianPrice); err != nil {
			continue
		}

		batch.Append(
			today, country, make_, uint16(year), fuelType,
			uint64(fleetCount), uint32(expectedForSale), uint32(observedCount),
			float32(cov), econValue, medianPrice,
		)
		count++
	}

	if err := batch.Send(); err != nil {
		slog.Error("census: ch batch send failed", "error", err)
		return
	}

	slog.Info("census: ClickHouse replication complete", "rows", count)
}

// pruneOld removes old coverage snapshots.
func (d *Deps) pruneOld(ctx context.Context) {
	if err := coverage.PruneOldSnapshots(ctx, d.pg); err != nil {
		slog.Error("census: prune failed", "error", err)
	}
}

// --- Scheduling helpers (identical to scheduler service) ---

func every(ctx context.Context, interval time.Duration, fn func(context.Context)) {
	fn(ctx) // run immediately
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			fn(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func dailyAt(ctx context.Context, utcHour int, fn func(context.Context)) {
	for {
		now := time.Now().UTC()
		next := time.Date(now.Year(), now.Month(), now.Day(), utcHour, 0, 0, 0, time.UTC)
		if !next.After(now) {
			next = next.Add(24 * time.Hour)
		}
		select {
		case <-time.After(time.Until(next)):
			fn(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func weeklyOn(ctx context.Context, day time.Weekday, utcHour int, fn func(context.Context)) {
	for {
		now := time.Now().UTC()
		next := time.Date(now.Year(), now.Month(), now.Day(), utcHour, 0, 0, 0, time.UTC)
		for next.Weekday() != day || !next.After(now) {
			next = next.Add(24 * time.Hour)
		}
		select {
		case <-time.After(time.Until(next)):
			fn(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
