package main

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/cardex/frontier/pkg/scoring"
)

type Deps struct {
	pg     *pgxpool.Pool
	ch     clickhouse.Conn
	rdb    *redis.Client
	scorer *scoring.CompositeScorer
}

func mustConnect(ctx context.Context) *Deps {
	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@postgres:5432/cardex")
	pg, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("frontier: postgres connect failed", "error", err)
		os.Exit(1)
	}
	if err = pg.Ping(ctx); err != nil {
		slog.Error("frontier: postgres ping failed", "error", err)
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
		slog.Error("frontier: clickhouse open failed", "error", err)
		os.Exit(1)
	}
	if err = ch.Ping(ctx); err != nil {
		slog.Error("frontier: clickhouse ping failed", "error", err)
		os.Exit(1)
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:     envOrDefault("REDIS_ADDR", "redis:6379"),
		PoolSize: 10,
	})
	if err = rdb.Ping(ctx).Err(); err != nil {
		slog.Error("frontier: redis ping failed", "error", err)
		os.Exit(1)
	}

	slog.Info("frontier: all connections established")
	return &Deps{
		pg:     pg,
		ch:     ch,
		rdb:    rdb,
		scorer: scoring.NewCompositeScorer(),
	}
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

	slog.Info("frontier: service started")

	// Warm start: seed initial priorities from census data so scrapers
	// have guidance immediately, even before the first full recompute completes.
	d.warmStart(ctx)

	// Recompute all crawl priorities every 30 minutes
	go every(ctx, 30*time.Minute, d.recomputeAllPriorities)

	// Update Thompson Sampling parameters from scraper results every hour
	go every(ctx, time.Hour, d.updateThompsonParams)

	// Persist frontier state to PostgreSQL every 2 hours
	go every(ctx, 2*time.Hour, d.persistFrontierState)

	<-ctx.Done()
	slog.Info("frontier: shutting down")
}

// recomputeAllPriorities reads coverage data from Redis, computes priority scores
// for all (platform, country, make, year) shards, and publishes sorted sets to Redis.
func (d *Deps) recomputeAllPriorities(ctx context.Context) {
	slog.Info("frontier: recomputing priorities")
	start := time.Now()

	// Get all coverage entries from the latest coverage_matrix
	rows, err := d.pg.Query(ctx, `
		SELECT DISTINCT ON (country, make, year)
			country, make, year,
			fleet_count, expected_for_sale, observed_count,
			coverage, economic_value_eur, median_price_eur
		FROM coverage_matrix
		ORDER BY country, make, year, computed_at DESC
	`)
	if err != nil {
		slog.Error("frontier: coverage query failed", "error", err)
		return
	}
	defer rows.Close()

	type coverageCell struct {
		Country         string
		Make            string
		Year            int
		FleetCount      int64
		ExpectedForSale int
		ObservedCount   int
		Coverage        float64
		EconomicValue   float64
		MedianPrice     float64
	}

	var cells []coverageCell
	for rows.Next() {
		var c coverageCell
		if err := rows.Scan(&c.Country, &c.Make, &c.Year,
			&c.FleetCount, &c.ExpectedForSale, &c.ObservedCount,
			&c.Coverage, &c.EconomicValue, &c.MedianPrice); err != nil {
			continue
		}
		cells = append(cells, c)
	}

	if len(cells) == 0 {
		slog.Warn("frontier: no coverage data available, skipping priority computation")
		return
	}

	// Find max economic value for normalization
	var maxEconValue float64
	for _, c := range cells {
		if c.EconomicValue > maxEconValue {
			maxEconValue = c.EconomicValue
		}
	}
	if maxEconValue == 0 {
		maxEconValue = 1 // avoid division by zero
	}

	// Get last crawl timestamps from crawl_frontier table
	lastCrawled := make(map[string]time.Time)
	lcRows, err := d.pg.Query(ctx, `SELECT platform, country, make, year, last_crawled_at FROM crawl_frontier WHERE last_crawled_at IS NOT NULL`)
	if err == nil {
		defer lcRows.Close()
		for lcRows.Next() {
			var platform, country, make_ string
			var year int
			var ts time.Time
			if lcRows.Scan(&platform, &country, &make_, &year, &ts) == nil {
				key := country + ":" + make_ + ":" + itoa(year)
				lastCrawled[key] = ts
			}
		}
	}

	// Get Thompson Sampling params from crawl_frontier
	thompsonParams := make(map[string][2]int) // key → [alpha, beta]
	tpRows, err := d.pg.Query(ctx, `SELECT country, make, year, thompson_alpha, thompson_beta FROM crawl_frontier`)
	if err == nil {
		defer tpRows.Close()
		for tpRows.Next() {
			var country, make_ string
			var year, alpha, beta int
			if tpRows.Scan(&country, &make_, &year, &alpha, &beta) == nil {
				key := country + ":" + make_ + ":" + itoa(year)
				thompsonParams[key] = [2]int{alpha, beta}
			}
		}
	}

	// Build demand signal from active price alerts (make/year extracted from JSONB criteria)
	demandMap := make(map[string]float64) // "make:year" → normalized demand score
	demandRows, err := d.pg.Query(ctx, `
		SELECT LOWER(criteria->>'make') AS make,
		       (criteria->>'year')::int AS year,
		       COUNT(*) AS alert_count
		FROM price_alerts
		WHERE active = true
		  AND created_at > NOW() - INTERVAL '30 days'
		  AND criteria->>'make' IS NOT NULL
		  AND criteria->>'year' IS NOT NULL
		GROUP BY LOWER(criteria->>'make'), (criteria->>'year')::int
	`)
	if err != nil {
		slog.Warn("frontier: demand signal query failed, continuing with zero demand", "error", err)
	} else {
		defer demandRows.Close()

		type demandEntry struct {
			make_      string
			year       int
			alertCount int
		}
		var demandEntries []demandEntry
		var maxAlertCount int
		for demandRows.Next() {
			var de demandEntry
			if err := demandRows.Scan(&de.make_, &de.year, &de.alertCount); err != nil {
				continue
			}
			demandEntries = append(demandEntries, de)
			if de.alertCount > maxAlertCount {
				maxAlertCount = de.alertCount
			}
		}
		// Normalize: demand = min(1.0, log1p(alertCount) / log1p(maxAlertCount))
		if maxAlertCount > 0 {
			denom := math.Log1p(float64(maxAlertCount))
			for _, de := range demandEntries {
				key := fmt.Sprintf("%s:%d", de.make_, de.year)
				score := math.Log1p(float64(de.alertCount)) / denom
				if score > 1.0 {
					score = 1.0
				}
				demandMap[key] = score
			}
			slog.Info("frontier: demand signal loaded", "entries", len(demandEntries), "max_alerts", maxAlertCount)
		}
	}

	// Platforms we publish priorities for
	// Each platform gets priorities for the countries it covers
	platforms := []struct {
		Platform string
		Country  string
	}{
		{"autoscout24_de", "DE"}, {"mobile_de", "DE"}, {"kleinanzeigen_de", "DE"},
		{"heycar_de", "DE"}, {"pkw_de", "DE"}, {"automobile_de", "DE"}, {"autohero_de", "DE"},
		{"autoscout24_es", "ES"}, {"coches_net", "ES"}, {"milanuncios", "ES"},
		{"wallapop", "ES"}, {"autocasion", "ES"}, {"motor_es", "ES"}, {"coches_com", "ES"}, {"flexicar", "ES"},
		{"autoscout24_fr", "FR"}, {"leboncoin", "FR"}, {"lacentrale", "FR"},
		{"paruvendu", "FR"}, {"largus_fr", "FR"}, {"caradisiac_fr", "FR"}, {"ouestfrance_auto", "FR"},
		{"autoscout24_nl", "NL"}, {"marktplaats", "NL"}, {"autotrack", "NL"}, {"gaspedaal", "NL"},
		{"autoscout24_be", "BE"}, {"2dehands", "BE"}, {"gocar", "BE"},
		{"autoscout24_ch", "CH"}, {"tutti", "CH"}, {"comparis", "CH"},
	}

	pipe := d.rdb.Pipeline()
	totalShards := 0

	for _, p := range platforms {
		key := "frontier:priorities:" + p.Platform
		// Clear old priorities
		pipe.Del(ctx, key)

		for _, c := range cells {
			if c.Country != p.Country {
				continue
			}

			cellKey := c.Country + ":" + c.Make + ":" + itoa(c.Year)

			// Compute component scores
			infoGain := d.scorer.InformationGain(c.Coverage)
			econNorm := c.EconomicValue / maxEconValue

			freshness := 0.5 // default mid-range
			if ts, ok := lastCrawled[cellKey]; ok {
				freshness = d.scorer.FreshnessDecay(time.Since(ts))
			}

			thompson := 0.5 // default
			if params, ok := thompsonParams[cellKey]; ok {
				thompson = d.scorer.ThompsonSample(params[0], params[1])
			}

			// Look up demand signal from price alerts
			demandKey := strings.ToLower(c.Make) + ":" + itoa(c.Year)
			demand := demandMap[demandKey] // 0 if no alerts exist

			priority := d.scorer.Composite(infoGain, econNorm, freshness, demand, thompson)

			member := c.Make + ":" + itoa(c.Year)
			pipe.ZAdd(ctx, key, redis.Z{Score: priority, Member: member})
			totalShards++
		}

		// Set TTL on the sorted set
		pipe.Expire(ctx, key, 2*time.Hour)
	}

	if _, err := pipe.Exec(ctx); err != nil {
		slog.Error("frontier: redis pipeline failed", "error", err)
		return
	}

	slog.Info("frontier: priorities published",
		"platforms", len(platforms),
		"shards", totalShards,
		"duration_ms", time.Since(start).Milliseconds(),
	)
}

// updateThompsonParams reads scraper result reports from Redis and updates
// the Thompson Sampling alpha/beta parameters in crawl_frontier.
func (d *Deps) updateThompsonParams(ctx context.Context) {
	slog.Info("frontier: updating Thompson Sampling params")

	// Read results from Redis hashes set by scrapers
	// Key pattern: frontier:results:{platform}:{country}
	// Field: "{make}:{year}", Value: count of NEW listings found
	keys, err := d.rdb.Keys(ctx, "frontier:results:*").Result()
	if err != nil {
		slog.Error("frontier: keys scan failed", "error", err)
		return
	}

	updated := 0
	for _, key := range keys {
		results, err := d.rdb.HGetAll(ctx, key).Result()
		if err != nil {
			continue
		}

		// Parse platform and country from key
		// frontier:results:{platform}:{country}
		parts := splitKey(key)
		if len(parts) < 4 {
			continue
		}
		platform := parts[2]
		country := parts[3]

		for field, val := range results {
			makeYear := splitMakeYear(field)
			if makeYear == nil {
				continue
			}

			newCount := atoi(val)
			// If scraper found new listings → success (increment alpha)
			// If scraper found 0 new listings → failure (increment beta)
			alphaInc, betaInc := 0, 1
			if newCount > 0 {
				alphaInc, betaInc = 1, 0
			}

			_, err := d.pg.Exec(ctx, `
				INSERT INTO crawl_frontier (platform, country, make, year, thompson_alpha, thompson_beta, listings_new, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
				ON CONFLICT (platform, country, make, year) DO UPDATE SET
					thompson_alpha = crawl_frontier.thompson_alpha + $5,
					thompson_beta = crawl_frontier.thompson_beta + $6,
					listings_new = crawl_frontier.listings_new + $7,
					updated_at = NOW()
			`, platform, country, makeYear[0], makeYear[1], alphaInc, betaInc, newCount)
			if err != nil {
				slog.Warn("frontier: thompson upsert failed", "error", err)
				continue
			}
			updated++
		}

		// Clear processed results
		d.rdb.Del(ctx, key)
	}

	slog.Info("frontier: Thompson params updated", "shards", updated)
}

// persistFrontierState writes current priority scores to crawl_frontier for durability.
func (d *Deps) persistFrontierState(ctx context.Context) {
	slog.Info("frontier: persisting state")

	keys, err := d.rdb.Keys(ctx, "frontier:priorities:*").Result()
	if err != nil {
		return
	}

	count := 0
	for _, key := range keys {
		parts := splitKey(key)
		if len(parts) < 3 {
			continue
		}
		platform := parts[2]

		members, err := d.rdb.ZRangeWithScores(ctx, key, 0, -1).Result()
		if err != nil {
			continue
		}

		for _, m := range members {
			makeYear := splitMakeYear(m.Member.(string))
			if makeYear == nil {
				continue
			}

			// Determine country from platform suffix
			country := platformCountry(platform)

			_, err := d.pg.Exec(ctx, `
				INSERT INTO crawl_frontier (platform, country, make, year, priority_score, updated_at)
				VALUES ($1, $2, $3, $4, $5, NOW())
				ON CONFLICT (platform, country, make, year) DO UPDATE SET
					priority_score = $5,
					updated_at = NOW()
			`, platform, country, makeYear[0], makeYear[1], m.Score)
			if err == nil {
				count++
			}
		}
	}

	slog.Info("frontier: state persisted", "shards", count)
}

// warmStart publishes initial priorities based on fleet census data.
// Called once at startup to ensure scrapers have guidance immediately,
// even before the first full recompute cycle completes.
func (d *Deps) warmStart(ctx context.Context) {
	slog.Info("frontier: warm start — seeding initial priorities from census")

	// Query coverage matrix for segments with lowest coverage (highest information gain)
	rows, err := d.pg.Query(ctx, `
		SELECT country, make, year,
		       COALESCE(coverage, 0) AS coverage,
		       COALESCE(economic_value_eur, 0) AS econ_value
		FROM coverage_matrix
		WHERE coverage < 0.5
		ORDER BY economic_value_eur DESC NULLS LAST
		LIMIT 5000
	`)
	if err != nil {
		slog.Warn("frontier: warm start query failed, scrapers will use fallback", "error", err)
		return
	}
	defer rows.Close()

	// Build per-platform priority sets
	type entry struct {
		member string
		score  float64
	}
	platformEntries := make(map[string][]entry)

	for rows.Next() {
		var country, make_ string
		var year int
		var coverage, econValue float64
		if rows.Scan(&country, &make_, &year, &coverage, &econValue) != nil {
			continue
		}
		// Simple priority: economic value x (1 - coverage)
		score := econValue * (1.0 - coverage)
		member := fmt.Sprintf("%s:%d", make_, year)

		// Map country to platforms (each country has specific portals)
		platforms := countryToPlatforms(country)
		for _, p := range platforms {
			platformEntries[p] = append(platformEntries[p], entry{member, score})
		}
	}

	if len(platformEntries) == 0 {
		slog.Warn("frontier: warm start found no low-coverage segments, scrapers will use fallback")
		return
	}

	// Publish to Redis
	pipe := d.rdb.Pipeline()
	for platform, entries := range platformEntries {
		key := fmt.Sprintf("frontier:priorities:%s", platform)
		zMembers := make([]redis.Z, len(entries))
		for i, e := range entries {
			zMembers[i] = redis.Z{Score: e.score, Member: e.member}
		}
		pipe.ZAdd(ctx, key, zMembers...)
		pipe.Expire(ctx, key, 2*time.Hour)
	}
	_, err = pipe.Exec(ctx)
	if err != nil {
		slog.Warn("frontier: warm start Redis publish failed", "error", err)
		return
	}

	total := 0
	for _, entries := range platformEntries {
		total += len(entries)
	}
	slog.Info("frontier: warm start complete", "platforms", len(platformEntries), "entries", total)
}

// countryToPlatforms maps a country code to the list of scraper platforms
// that cover that market.
func countryToPlatforms(country string) []string {
	switch country {
	case "DE":
		return []string{"autoscout24_de", "mobile_de", "kleinanzeigen_de", "heycar_de", "pkw_de", "automobile_de", "autohero_de"}
	case "ES":
		return []string{"autoscout24_es", "coches_net", "milanuncios", "wallapop", "autocasion", "motor_es", "coches_com", "flexicar"}
	case "FR":
		return []string{"autoscout24_fr", "leboncoin", "lacentrale", "paruvendu", "largus_fr", "caradisiac_fr", "ouestfrance_auto"}
	case "NL":
		return []string{"autoscout24_nl", "marktplaats", "autotrack", "gaspedaal"}
	case "BE":
		return []string{"autoscout24_be", "2dehands", "gocar"}
	case "CH":
		return []string{"autoscout24_ch", "tutti", "comparis"}
	default:
		return nil
	}
}

// --- Helpers ---

func every(ctx context.Context, interval time.Duration, fn func(context.Context)) {
	fn(ctx)
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

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func itoa(n int) string {
	return strconv.Itoa(n)
}

func atoi(s string) int {
	n, _ := strconv.Atoi(s)
	return n
}

func splitKey(key string) []string {
	return splitBy(key, ':')
}

func splitMakeYear(s string) []interface{} {
	// "BMW:2020" → ["BMW", 2020]
	idx := -1
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == ':' {
			idx = i
			break
		}
	}
	if idx < 0 {
		return nil
	}
	make_ := s[:idx]
	year := atoi(s[idx+1:])
	if year < 1970 || year > 2030 {
		return nil
	}
	return []interface{}{make_, year}
}

func splitBy(s string, sep byte) []string {
	var result []string
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == sep {
			result = append(result, s[start:i])
			start = i + 1
		}
	}
	result = append(result, s[start:])
	return result
}

func platformCountry(platform string) string {
	// Extract country from platform name suffix
	if len(platform) >= 3 {
		suffix := platform[len(platform)-2:]
		switch suffix {
		case "de":
			return "DE"
		case "es":
			return "ES"
		case "fr":
			return "FR"
		case "nl":
			return "NL"
		case "be":
			return "BE"
		case "ch":
			return "CH"
		}
	}
	// Special cases
	switch {
	case contains(platform, "mobile_de") || contains(platform, "kleinanzeigen") || contains(platform, "heycar") || contains(platform, "pkw_de") || contains(platform, "autohero"):
		return "DE"
	case contains(platform, "wallapop") || contains(platform, "milanuncios") || contains(platform, "coches") || contains(platform, "autocasion") || contains(platform, "motor_es") || contains(platform, "flexicar"):
		return "ES"
	case contains(platform, "leboncoin") || contains(platform, "lacentrale") || contains(platform, "paruvendu") || contains(platform, "largus") || contains(platform, "caradisiac") || contains(platform, "ouestfrance"):
		return "FR"
	case contains(platform, "marktplaats") || contains(platform, "autotrack") || contains(platform, "gaspedaal"):
		return "NL"
	case contains(platform, "2dehands") || contains(platform, "gocar"):
		return "BE"
	case contains(platform, "tutti") || contains(platform, "comparis"):
		return "CH"
	}
	return ""
}

func contains(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

