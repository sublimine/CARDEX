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
	"fmt"
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

// materializePriceCandles computes OHLCV candles (weekly + monthly) per
// make/model/year/country/fuel_type and upserts into cardex.price_candles.
// Run nightly at 02:30 UTC after scrape jobs have ingested fresh listings.
func (d *Deps) materializePriceCandles(ctx context.Context) {
	log.Println("[job] materializePriceCandles: start")

	// Weekly candles — last 104 weeks (2 years rolling)
	weeklyQ := `
		INSERT INTO cardex.price_candles
			(period_start, period_type, make, model, year, country, fuel_type,
			 open_eur, high_eur, low_eur, close_eur, volume, avg_mileage_km, avg_dom)
		SELECT
			toStartOfWeek(toDate(first_seen_at))   AS period_start,
			'W'                                    AS period_type,
			make,
			model,
			year,
			origin_country                         AS country,
			fuel_type,
			quantile(0.10)(net_landed_cost_eur)    AS open_eur,
			quantile(0.90)(net_landed_cost_eur)    AS high_eur,
			quantile(0.05)(net_landed_cost_eur)    AS low_eur,
			median(net_landed_cost_eur)            AS close_eur,
			count()                                AS volume,
			avg(mileage_km)                        AS avg_mileage_km,
			avg(days_on_market)                    AS avg_dom
		FROM cardex.vehicle_inventory
		WHERE
			net_landed_cost_eur > 500
			AND net_landed_cost_eur < 500000
			AND first_seen_at >= now() - INTERVAL 2 YEAR
			AND make != ''
			AND model != ''
			AND year > 1990
			AND origin_country IN ('DE','ES','FR','NL','BE','CH')
		GROUP BY period_start, make, model, year, country, fuel_type
		HAVING volume >= 5
	`
	if err := d.ch.Exec(ctx, weeklyQ); err != nil {
		log.Printf("[job] materializePriceCandles weekly: %v", err)
	} else {
		log.Println("[job] materializePriceCandles: weekly candles done")
	}

	// Monthly candles — last 5 years rolling
	monthlyQ := `
		INSERT INTO cardex.price_candles
			(period_start, period_type, make, model, year, country, fuel_type,
			 open_eur, high_eur, low_eur, close_eur, volume, avg_mileage_km, avg_dom)
		SELECT
			toStartOfMonth(toDate(first_seen_at))  AS period_start,
			'M'                                    AS period_type,
			make,
			model,
			year,
			origin_country                         AS country,
			fuel_type,
			quantile(0.10)(net_landed_cost_eur)    AS open_eur,
			quantile(0.90)(net_landed_cost_eur)    AS high_eur,
			quantile(0.05)(net_landed_cost_eur)    AS low_eur,
			median(net_landed_cost_eur)            AS close_eur,
			count()                                AS volume,
			avg(mileage_km)                        AS avg_mileage_km,
			avg(days_on_market)                    AS avg_dom
		FROM cardex.vehicle_inventory
		WHERE
			net_landed_cost_eur > 500
			AND net_landed_cost_eur < 500000
			AND first_seen_at >= now() - INTERVAL 5 YEAR
			AND make != ''
			AND model != ''
			AND year > 1990
			AND origin_country IN ('DE','ES','FR','NL','BE','CH')
		GROUP BY period_start, make, model, year, country, fuel_type
		HAVING volume >= 10
	`
	if err := d.ch.Exec(ctx, monthlyQ); err != nil {
		log.Printf("[job] materializePriceCandles monthly: %v", err)
	} else {
		log.Println("[job] materializePriceCandles: monthly candles done")
	}
}

// computeTickerStats refreshes the ticker_stats table with last price,
// 1W/1M/3M % changes, 30-day volume, and liquidity score.
// Run nightly at 03:00 UTC after materializePriceCandles.
func (d *Deps) computeTickerStats(ctx context.Context) {
	log.Println("[job] computeTickerStats: start")
	q := `
		INSERT INTO cardex.ticker_stats
			(ticker_id, make, model, year, country, fuel_type,
			 last_price_eur, change_1w_pct, change_1m_pct, change_3m_pct,
			 volume_30d, avg_dom_30d, liquidity_score)
		SELECT
			concat(make, '_', replaceAll(model, ' ', '-'), '_', toString(year), '_', country, '_', fuel_type) AS ticker_id,
			make,
			model,
			year,
			country,
			fuel_type,
			-- Last close price (most recent monthly candle)
			argMax(close_eur, period_start)  AS last_price_eur,

			-- 1-week change %
			if(
				countIf(period_start = toStartOfWeek(today() - toIntervalWeek(1))) > 0,
				(argMax(close_eur, period_start) - argMaxIf(close_eur, period_start, period_start = toStartOfWeek(today() - toIntervalWeek(1))))
				/ nullIf(argMaxIf(close_eur, period_start, period_start = toStartOfWeek(today() - toIntervalWeek(1))), 0) * 100,
				0
			) AS change_1w_pct,

			-- 1-month change %
			if(
				countIf(period_start = toStartOfMonth(today() - toIntervalMonth(1))) > 0,
				(argMax(close_eur, period_start) - argMaxIf(close_eur, period_start, period_start = toStartOfMonth(today() - toIntervalMonth(1))))
				/ nullIf(argMaxIf(close_eur, period_start, period_start = toStartOfMonth(today() - toIntervalMonth(1))), 0) * 100,
				0
			) AS change_1m_pct,

			-- 3-month change %
			if(
				countIf(period_start = toStartOfMonth(today() - toIntervalMonth(3))) > 0,
				(argMax(close_eur, period_start) - argMaxIf(close_eur, period_start, period_start = toStartOfMonth(today() - toIntervalMonth(3))))
				/ nullIf(argMaxIf(close_eur, period_start, period_start = toStartOfMonth(today() - toIntervalMonth(3))), 0) * 100,
				0
			) AS change_3m_pct,

			-- 30-day volume (sum weekly volume last ~4 weeks)
			sumIf(volume, period_start >= today() - 30 AND period_type = 'W') AS volume_30d,

			-- Avg DOM last 30d (from weekly candles)
			avgIf(avg_dom, period_start >= today() - 30 AND period_type = 'W') AS avg_dom_30d,

			-- Liquidity score = 0-1: combines volume_30d rank and low avg_dom
			-- Simple formula: min(1, volume_30d / 500) * 0.7 + max(0, 1 - avg_dom_30d / 90) * 0.3
			least(1.0, toFloat32(volume_30d) / 500.0) * 0.7
			+ greatest(0.0, 1.0 - toFloat32(avg_dom_30d) / 90.0) * 0.3 AS liquidity_score

		FROM cardex.price_candles
		WHERE period_start >= today() - INTERVAL 3 MONTH
		GROUP BY make, model, year, country, fuel_type
		HAVING last_price_eur > 0 AND volume_30d >= 5
		ORDER BY volume_30d DESC
		LIMIT 500
	`
	if err := d.ch.Exec(ctx, q); err != nil {
		log.Printf("[job] computeTickerStats: %v", err)
		return
	}
	log.Println("[job] computeTickerStats: done")
}

// computeArbitrageOpportunities scans price_index for cross-country median price
// gaps that exceed NLC (logistics + destination tax), then upserts viable
// arbitrage opportunities into cardex.arbitrage_opportunities.
// Run hourly.
func (d *Deps) computeArbitrageOpportunities(ctx context.Context) {
	log.Println("[job] computeArbitrageOpportunities: start")

	// NLC cost matrix (logistics EUR + avg destination tax by route).
	// These are approximate values; Phase 2 will call the actual alpha/nlc service.
	type route struct {
		origin, dest                string
		logisticsEUR                float64
		destTaxPctGasoline          float64 // IEDMT/Malus/BPM equivalent as flat avg pct
		oppType                     string
	}
	routes := []route{
		// DE → ES: IEDMT 4.75-9.75% avg, transport ~€850
		{"DE", "ES", 850, 0.0675, "PRICE_DIFF"},
		// DE → FR: Malus avg ~€800 for typical 130g/km car, transport ~€700
		{"DE", "FR", 700, 0.025, "PRICE_DIFF"},
		// FR → ES: IEDMT 4.75%, transport ~€500
		{"FR", "ES", 500, 0.0475, "PRICE_DIFF"},
		// FR → BE: TMC ~€60 flat, transport ~€400
		{"FR", "BE", 400, 0.005, "PRICE_DIFF"},
		// NL → DE: No reg tax in DE, BPM refund = bonus (handled separately), transport ~€400
		{"NL", "DE", 400, 0.0, "BPM_EXPORT"},
		// NL → BE: TMC ~€60, transport ~€300
		{"NL", "BE", 300, 0.005, "BPM_EXPORT"},
		// CH → DE: EUR.1 duty-free, Swiss Automobilsteuer already paid, transport ~€600
		{"CH", "DE", 600, 0.0, "PRICE_DIFF"},
		// BE → FR: Malus avg, transport ~€400
		{"BE", "FR", 400, 0.025, "PRICE_DIFF"},
	}

	for _, rt := range routes {
		q := `
			SELECT
				o.make,
				o.model,
				o.year,
				o.fuel_type,
				o.median_eur   AS origin_median,
				d.median_eur   AS dest_median,
				o.volume       AS sample_origin,
				d.volume       AS sample_dest,
				o.avg_co2_gkm  AS co2_gkm,
				-- example listing URL (pick one from vehicle_inventory)
				''             AS example_url
			FROM (
				SELECT make, model, year, fuel_type,
					   median(net_landed_cost_eur) AS median_eur,
					   count() AS volume,
					   avg(co2_gkm) AS avg_co2_gkm
				FROM cardex.vehicle_inventory
				WHERE origin_country = ?
				  AND lifecycle_status = 'ACTIVE'
				  AND net_landed_cost_eur > 1000
				  AND first_seen_at >= now() - INTERVAL 30 DAY
				  AND make != '' AND model != '' AND year > 2005
				GROUP BY make, model, year, fuel_type
				HAVING volume >= 10
			) o
			JOIN (
				SELECT make, model, year, fuel_type,
					   median(net_landed_cost_eur) AS median_eur,
					   count() AS volume
				FROM cardex.vehicle_inventory
				WHERE origin_country = ?
				  AND lifecycle_status = 'ACTIVE'
				  AND net_landed_cost_eur > 1000
				  AND first_seen_at >= now() - INTERVAL 30 DAY
				  AND make != '' AND model != '' AND year > 2005
				GROUP BY make, model, year, fuel_type
				HAVING volume >= 5
			) d ON o.make = d.make AND o.model = d.model AND o.year = d.year AND o.fuel_type = d.fuel_type
			WHERE dest_median > origin_median * 1.03
			ORDER BY (dest_median - origin_median) DESC
			LIMIT 50
		`

		type oppRow struct {
			Make         string
			Model        string
			Year         uint16
			FuelType     string
			OriginMedian float64
			DestMedian   float64
			SampleOrigin uint32
			SampleDest   uint32
			CO2GKM       uint16
			ExampleURL   string
		}

		chRows, err := d.ch.Query(ctx, q, rt.origin, rt.dest)
		if err != nil {
			log.Printf("[job] computeArbitrageOpportunities %s→%s: query: %v", rt.origin, rt.dest, err)
			continue
		}

		var opps []oppRow
		for chRows.Next() {
			var o oppRow
			if err := chRows.Scan(&o.Make, &o.Model, &o.Year, &o.FuelType,
				&o.OriginMedian, &o.DestMedian, &o.SampleOrigin, &o.SampleDest,
				&o.CO2GKM, &o.ExampleURL); err != nil {
				continue
			}
			opps = append(opps, o)
		}
		chRows.Close()

		if len(opps) == 0 {
			continue
		}

		// Build INSERT batch
		batch, err := d.ch.PrepareBatch(ctx, `
			INSERT INTO cardex.arbitrage_opportunities
				(opportunity_id, opportunity_type, make, model, year, fuel_type,
				 origin_country, dest_country, origin_median_eur, dest_median_eur,
				 nlc_estimate_eur, gross_margin_eur, margin_pct, confidence_score,
				 sample_size_origin, sample_size_dest, co2_gkm,
				 bpm_refund_eur, iedmt_eur, malus_eur, example_listing_url, status)
		`)
		if err != nil {
			log.Printf("[job] computeArbitrageOpportunities %s→%s: prepare: %v", rt.origin, rt.dest, err)
			continue
		}

		inserted := 0
		for _, o := range opps {
			destTax := o.OriginMedian * rt.destTaxPctGasoline
			nlc := rt.logisticsEUR + destTax

			// BPM refund estimate for NL exports (simplified: high-CO2 cars)
			bpmRefund := 0.0
			if rt.origin == "NL" && o.CO2GKM > 150 {
				// Rough BPM refund: ~€6,000 for 150g/km diesel, scaling up
				bpmRefund = float64(o.CO2GKM-100) * 60.0
				if bpmRefund > 20000 {
					bpmRefund = 20000
				}
				nlc -= bpmRefund // BPM refund reduces effective cost
			}

			iedmtEUR := 0.0
			if rt.dest == "ES" {
				iedmtEUR = destTax
			}
			malusEUR := 0.0
			if rt.dest == "FR" {
				malusEUR = destTax
			}

			grossMargin := o.DestMedian - o.OriginMedian - nlc
			if grossMargin < 300 {
				continue // Not worth it
			}
			marginPct := grossMargin / o.OriginMedian * 100

			// Confidence: based on sample sizes and margin
			confidence := float32(0.3)
			if o.SampleOrigin >= 50 {
				confidence += 0.3
			} else if o.SampleOrigin >= 20 {
				confidence += 0.15
			}
			if o.SampleDest >= 20 {
				confidence += 0.2
			} else if o.SampleDest >= 10 {
				confidence += 0.1
			}
			if marginPct > 10 {
				confidence += 0.2
			} else if marginPct > 5 {
				confidence += 0.1
			}
			if confidence > 1.0 {
				confidence = 1.0
			}

			// Deterministic opportunity_id
			oppID := fmt.Sprintf("%s_%s_%s_%d_%s_%s",
				rt.origin, rt.dest, o.Make, o.Year, o.Model, o.FuelType)

			if err := batch.Append(
				oppID, rt.oppType, o.Make, o.Model, o.Year, o.FuelType,
				rt.origin, rt.dest, o.OriginMedian, o.DestMedian,
				nlc, grossMargin, float32(marginPct), confidence,
				o.SampleOrigin, o.SampleDest, o.CO2GKM,
				bpmRefund, iedmtEUR, malusEUR, o.ExampleURL, "ACTIVE",
			); err != nil {
				log.Printf("[job] computeArbitrageOpportunities batch append: %v", err)
				continue
			}
			inserted++
		}

		if inserted > 0 {
			if err := batch.Send(); err != nil {
				log.Printf("[job] computeArbitrageOpportunities %s→%s: send: %v", rt.origin, rt.dest, err)
			} else {
				log.Printf("[job] computeArbitrageOpportunities %s→%s: inserted %d opportunities", rt.origin, rt.dest, inserted)
			}
		}
	}
	log.Println("[job] computeArbitrageOpportunities: done")
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

	// TradingCar: price candles nightly at 02:30 UTC
	go dailyAt(ctx, 2, d.materializePriceCandles)

	// TradingCar: ticker stats nightly at 03:00 UTC (after candles)
	go dailyAt(ctx, 3, d.computeTickerStats)

	// Arbitrage scanner: every hour
	go every(ctx, time.Hour, d.computeArbitrageOpportunities)

	<-ctx.Done()
	log.Println("scheduler: shutting down")
}
