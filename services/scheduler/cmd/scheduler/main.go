// Scheduler: periodic job orchestration for CARDEX.
// Jobs:
//   - Price index materialization (every 4h)
//   - FX rate refresh (every 6h) — EUR/CHF, EUR/GBP
//   - Stale listing expiry (daily 03:00 UTC)
//   - Scrape job dispatch (nightly, per-platform per-country)
//   - VIN cache pruning (weekly Sunday 02:00 UTC)
//   - ClickHouse OPTIMIZE (weekly, MergeTree maintenance)
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// ── Config ────────────────────────────────────────────────────────────────────

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// ── Deps ──────────────────────────────────────────────────────────────────────

type Deps struct {
	pg  *pgxpool.Pool
	ch  clickhouse.Conn
	rdb *redis.Client
}

func mustConnect(ctx context.Context) *Deps {
	pg, err := pgxpool.New(ctx, env("DATABASE_URL", "postgres://cardex:cardex@postgres:5432/cardex"))
	if err != nil {
		log.Fatalf("scheduler: postgres connect: %v", err)
	}
	if err = pg.Ping(ctx); err != nil {
		log.Fatalf("scheduler: postgres ping: %v", err)
	}

	ch, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{env("CLICKHOUSE_ADDR", "clickhouse:9000")},
		Auth: clickhouse.Auth{
			Database: "cardex",
			Username: env("CLICKHOUSE_USER", "default"),
			Password: env("CLICKHOUSE_PASSWORD", ""),
		},
		DialTimeout:     10 * time.Second,
		MaxOpenConns:    4,
		MaxIdleConns:    2,
		ConnMaxLifetime: time.Hour,
	})
	if err != nil {
		log.Fatalf("scheduler: clickhouse open: %v", err)
	}
	if err = ch.Ping(ctx); err != nil {
		log.Fatalf("scheduler: clickhouse ping: %v", err)
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:     env("REDIS_ADDR", "redis:6379"),
		PoolSize: 10,
	})
	if err = rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("scheduler: redis ping: %v", err)
	}

	log.Println("scheduler: all connections established")
	return &Deps{pg: pg, ch: ch, rdb: rdb}
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

// materializePriceIndex computes OHLCV aggregations into price_index from
// vehicle_inventory events accumulated since the last run.
func (d *Deps) materializePriceIndex(ctx context.Context) {
	log.Println("[job] materializePriceIndex: start")
	q := `
		INSERT INTO cardex.price_index
			(ts, make, model, source_country, interval_type,
			 open_price, high_price, low_price, close_price,
			 p5_price, p25_price, median_price, p75_price, p90_price,
			 sample_size, avg_dom)
		SELECT
			toStartOfHour(now())                             AS ts,
			make,
			model,
			source_country,
			'1h'                                             AS interval_type,
			quantile(0.10)(price_eur)                        AS open_price,
			quantile(0.90)(price_eur)                        AS high_price,
			quantile(0.05)(price_eur)                        AS low_price,
			median(price_eur)                                AS close_price,
			quantile(0.05)(price_eur)                        AS p5_price,
			quantile(0.25)(price_eur)                        AS p25_price,
			median(price_eur)                                AS median_price,
			quantile(0.75)(price_eur)                        AS p75_price,
			quantile(0.90)(price_eur)                        AS p90_price,
			count()                                          AS sample_size,
			avg(days_on_market)                              AS avg_dom
		FROM cardex.vehicle_inventory
		WHERE
			listing_status = 'ACTIVE'
			AND price_eur > 500
			AND price_eur < 500000
			AND scraped_at >= now() - INTERVAL 1 HOUR
		GROUP BY make, model, source_country
		HAVING sample_size >= 3
	`
	if err := d.ch.Exec(ctx, q); err != nil {
		log.Printf("[job] materializePriceIndex: %v", err)
		return
	}
	log.Println("[job] materializePriceIndex: done")
}

// expireStaleListings marks listings not seen in >14 days as SOLD/EXPIRED in
// PostgreSQL and publishes delete ops to stream:meili_sync.
func (d *Deps) expireStaleListings(ctx context.Context) {
	log.Println("[job] expireStaleListings: start")

	rows, err := d.pg.Query(ctx, `
		UPDATE vehicles
		SET listing_status = 'EXPIRED', updated_at = now()
		WHERE listing_status = 'ACTIVE'
		  AND scraped_at < now() - INTERVAL '14 days'
		RETURNING id
	`)
	if err != nil {
		log.Printf("[job] expireStaleListings query: %v", err)
		return
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			continue
		}
		// Publish delete op to meili-sync
		d.rdb.XAdd(ctx, &redis.XAddArgs{
			Stream: "stream:meili_sync",
			Values: map[string]interface{}{
				"op": "delete",
				"id": id,
			},
		})
		count++
	}
	log.Printf("[job] expireStaleListings: marked %d listings as EXPIRED", count)
}

// refreshFXRates fetches EUR/CHF and EUR/GBP rates from ECB daily XML feed
// and stores them in Redis for use by the pricing pipeline.
func (d *Deps) refreshFXRates(ctx context.Context) {
	log.Println("[job] refreshFXRates: start")
	// ECB publishes rates at ~16:00 CET daily.
	// For now we store static approximate rates; a production implementation
	// would parse https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
	// In dev environment we just set sensible defaults.
	rates := map[string]interface{}{
		"EUR_CHF": "0.94",
		"EUR_GBP": "0.85",
		"EUR_DKK": "7.46",
		"EUR_SEK": "11.28",
		"EUR_NOK": "11.72",
	}
	if err := d.rdb.HSet(ctx, "fx:rates", rates).Err(); err != nil {
		log.Printf("[job] refreshFXRates: %v", err)
		return
	}
	d.rdb.Expire(ctx, "fx:rates", 8*time.Hour)
	log.Println("[job] refreshFXRates: done")
}

// dispatchScrapeJobs publishes scrape-job messages to stream:scrape_dispatch
// so the scraper fleet can pick them up. Each message specifies platform,
// country, and whether it is a full or incremental pass.
func (d *Deps) dispatchScrapeJobs(ctx context.Context) {
	log.Println("[job] dispatchScrapeJobs: start")

	jobs := []map[string]interface{}{
		{"platform": "autoscout24", "country": "DE", "mode": "incremental"},
		{"platform": "autoscout24", "country": "ES", "mode": "incremental"},
		{"platform": "autoscout24", "country": "FR", "mode": "incremental"},
		{"platform": "autoscout24", "country": "BE", "mode": "incremental"},
		{"platform": "autoscout24", "country": "CH", "mode": "incremental"},
		{"platform": "mobile_de", "country": "DE", "mode": "incremental"},
		{"platform": "coches_net", "country": "ES", "mode": "incremental"},
		{"platform": "leboncoin", "country": "FR", "mode": "incremental"},
		{"platform": "marktplaats", "country": "NL", "mode": "incremental"},
		{"platform": "google_maps", "country": "ALL", "mode": "incremental"},
	}

	pipe := d.rdb.Pipeline()
	for _, job := range jobs {
		pipe.XAdd(ctx, &redis.XAddArgs{
			Stream: "stream:scrape_dispatch",
			Values: job,
		})
	}
	if _, err := pipe.Exec(ctx); err != nil {
		log.Printf("[job] dispatchScrapeJobs: %v", err)
		return
	}
	log.Printf("[job] dispatchScrapeJobs: dispatched %d jobs", len(jobs))
}

// pruneVINCache removes VIN history cache entries older than 90 days.
func (d *Deps) pruneVINCache(ctx context.Context) {
	log.Println("[job] pruneVINCache: start")
	tag, err := d.pg.Exec(ctx, `
		DELETE FROM vin_history_cache
		WHERE last_seen < now() - INTERVAL '90 days'
	`)
	if err != nil {
		log.Printf("[job] pruneVINCache: %v", err)
		return
	}
	log.Printf("[job] pruneVINCache: deleted %d stale VIN entries", tag.RowsAffected())
}

// optimizeClickHouse runs OPTIMIZE TABLE on MergeTree tables to force merge
// of parts and reclaim space. Run weekly off-peak.
func (d *Deps) optimizeClickHouse(ctx context.Context) {
	log.Println("[job] optimizeClickHouse: start")
	tables := []string{
		"cardex.price_index",
		"cardex.market_depth",
		"cardex.demand_signals",
		"cardex.dom_distribution",
	}
	for _, t := range tables {
		if err := d.ch.Exec(ctx, "OPTIMIZE TABLE "+t+" FINAL"); err != nil {
			log.Printf("[job] optimizeClickHouse %s: %v", t, err)
		}
	}
	log.Println("[job] optimizeClickHouse: done")
}

// ── Ticker helpers ─────────────────────────────────────────────────────────────

// every runs fn immediately then on each tick of interval.
func every(ctx context.Context, interval time.Duration, fn func(context.Context)) {
	fn(ctx) // run immediately on start
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

// dailyAt schedules fn to run once per day at the given UTC hour.
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

// weeklyOn schedules fn to run once per week on the given weekday at utcHour.
func weeklyOn(ctx context.Context, day time.Weekday, utcHour int, fn func(context.Context)) {
	for {
		now := time.Now().UTC()
		daysUntil := int(day - now.Weekday())
		if daysUntil < 0 {
			daysUntil += 7
		}
		next := time.Date(now.Year(), now.Month(), now.Day()+daysUntil, utcHour, 0, 0, 0, time.UTC)
		if !next.After(now) {
			next = next.Add(7 * 24 * time.Hour)
		}
		select {
		case <-time.After(time.Until(next)):
			fn(ctx)
		case <-ctx.Done():
			return
		}
	}
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	d := mustConnect(ctx)
	defer d.pg.Close()
	defer d.ch.Close()
	defer d.rdb.Close()

	log.Println("scheduler: starting job loops")

	// Price index: every 4 hours
	go every(ctx, 4*time.Hour, d.materializePriceIndex)

	// FX rates: every 6 hours
	go every(ctx, 6*time.Hour, d.refreshFXRates)

	// Stale listing expiry: daily at 03:00 UTC
	go dailyAt(ctx, 3, d.expireStaleListings)

	// Scrape dispatch: daily at 01:00 UTC (off-peak)
	go dailyAt(ctx, 1, d.dispatchScrapeJobs)

	// VIN cache prune: weekly Sunday at 02:00 UTC
	go weeklyOn(ctx, time.Sunday, 2, d.pruneVINCache)

	// ClickHouse OPTIMIZE: weekly Saturday at 04:00 UTC
	go weeklyOn(ctx, time.Saturday, 4, d.optimizeClickHouse)

	<-ctx.Done()
	log.Println("scheduler: shutting down")
}
