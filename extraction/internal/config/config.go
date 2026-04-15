// Package config loads extraction service configuration from environment variables.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds all configuration for the extraction service.
type Config struct {
	// DBPath is the path to the shared SQLite knowledge graph.
	// Should match DISCOVERY_DB_PATH used by the discovery service.
	// Default: ./data/discovery.db
	DBPath string

	// MetricsAddr is the HTTP listen address for the Prometheus /metrics endpoint.
	// Default: :9091 (9090 is used by discovery)
	MetricsAddr string

	// BatchSize is the number of dealers to process per extraction cycle.
	// Default: 50
	BatchSize int

	// WorkerCount is the number of concurrent dealer extractions.
	// Default: 4 (conservative; each worker makes HTTP requests)
	WorkerCount int

	// OneShot, when true, runs one extraction cycle and exits.
	// Default: false (daemon mode)
	OneShot bool

	// Countries restricts extraction to the given ISO-3166-1 country codes.
	// Default: ["FR"] (matching discovery default)
	Countries []string

	// CardexBotUA is the User-Agent sent in all extraction HTTP requests.
	CardexBotUA string

	// SkipE01, when true, disables the JSON-LD Schema.org strategy.
	SkipE01 bool

	// SkipE02, when true, disables the CMS REST endpoint strategy.
	SkipE02 bool

	// SkipE03, when true, disables the Sitemap XML strategy.
	SkipE03 bool

	// SkipE04, when true, disables the RSS/Atom feeds strategy.
	SkipE04 bool

	// SkipE05, when true, disables the DMS Hosted API strategy.
	SkipE05 bool

	// SkipE06, when true, disables the Microdata/RDFa strategy.
	SkipE06 bool

	// SkipE07, when true, disables the Playwright XHR strategy.
	SkipE07 bool

	// SkipE08, when true, disables the PDF Catalog strategy.
	SkipE08 bool

	// SkipE09, when true, disables the Excel/CSV Feeds strategy.
	SkipE09 bool

	// SkipE10, when true, disables the Email Inventory strategy (stub).
	SkipE10 bool

	// SkipE11, when true, disables the Manual Review Queue strategy.
	SkipE11 bool

	// SkipE12, when true, disables the Edge Dealer Push strategy.
	SkipE12 bool

	// EdgeGRPCPort is the port on which the gRPC edge push server listens.
	// Default: 50051
	EdgeGRPCPort int

	// RateLimitMs is the default inter-request sleep within a single dealer.
	// Strategies may override this per-dealer. Default: 2000 ms.
	RateLimitMs int
}

// Load builds a Config from environment variables.
func Load() (*Config, error) {
	c := &Config{
		DBPath:       getEnv("EXTRACTION_DB_PATH", "./data/discovery.db"),
		MetricsAddr:  getEnv("EXTRACTION_METRICS_ADDR", ":9091"),
		BatchSize:    50,
		WorkerCount:  4,
		Countries:    []string{"FR"},
		CardexBotUA:  "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)",
		RateLimitMs:  2000,
		EdgeGRPCPort: 50051,
	}

	if raw := os.Getenv("EXTRACTION_BATCH_SIZE"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: EXTRACTION_BATCH_SIZE must be a positive integer, got %q", raw)
		}
		c.BatchSize = n
	}

	if raw := os.Getenv("EXTRACTION_WORKERS"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: EXTRACTION_WORKERS must be a positive integer, got %q", raw)
		}
		c.WorkerCount = n
	}

	if raw := os.Getenv("EXTRACTION_RATE_LIMIT_MS"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n < 0 {
			return nil, fmt.Errorf("config: EXTRACTION_RATE_LIMIT_MS must be a non-negative integer, got %q", raw)
		}
		c.RateLimitMs = n
	}

	if os.Getenv("EXTRACTION_ONE_SHOT") == "true" {
		c.OneShot = true
	}
	if os.Getenv("EXTRACTION_SKIP_E01") == "true" {
		c.SkipE01 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E02") == "true" {
		c.SkipE02 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E03") == "true" {
		c.SkipE03 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E04") == "true" {
		c.SkipE04 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E05") == "true" {
		c.SkipE05 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E06") == "true" {
		c.SkipE06 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E07") == "true" {
		c.SkipE07 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E08") == "true" {
		c.SkipE08 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E09") == "true" {
		c.SkipE09 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E10") == "true" {
		c.SkipE10 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E11") == "true" {
		c.SkipE11 = true
	}
	if os.Getenv("EXTRACTION_SKIP_E12") == "true" {
		c.SkipE12 = true
	}

	if raw := os.Getenv("EDGE_GRPC_PORT"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 || n > 65535 {
			return nil, fmt.Errorf("config: EDGE_GRPC_PORT must be a valid port number, got %q", raw)
		}
		c.EdgeGRPCPort = n
	}

	if raw := os.Getenv("EXTRACTION_COUNTRIES"); raw != "" {
		parts := strings.Split(raw, ",")
		countries := make([]string, 0, len(parts))
		for _, p := range parts {
			if s := strings.TrimSpace(strings.ToUpper(p)); s != "" {
				countries = append(countries, s)
			}
		}
		if len(countries) > 0 {
			c.Countries = countries
		}
	}

	return c, nil
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
