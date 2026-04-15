// Package config loads quality service configuration from environment variables.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds all runtime configuration for the quality service.
type Config struct {
	// DBPath is the path to the shared SQLite knowledge graph.
	// Must match DISCOVERY_DB_PATH / EXTRACTION_DB_PATH used by peer services.
	// Default: ./data/discovery.db
	DBPath string

	// MetricsAddr is the HTTP bind address for the Prometheus /metrics endpoint.
	// Default: :9092 (9090 = discovery, 9091 = extraction)
	MetricsAddr string

	// BatchSize is the number of vehicles to validate per cycle.
	// Default: 100
	BatchSize int

	// WorkerCount is the number of concurrent validation workers.
	// Default: 4
	WorkerCount int

	// OneShot, when true, runs one validation cycle and exits.
	// Default: false (daemon mode)
	OneShot bool

	// Countries restricts validation to vehicles from these ISO-3166-1 codes.
	// Default: all
	Countries []string

	// SkipV01, when true, disables the VIN Checksum validator.
	SkipV01 bool

	// SkipV02, when true, disables the NHTSA vPIC validator.
	SkipV02 bool

	// SkipV03, when true, disables the DAT Codes validator.
	SkipV03 bool

	// SkipV04, when true, disables the NLP Make/Model validator.
	SkipV04 bool

	// SkipV05, when true, disables the Image Quality validator.
	SkipV05 bool

	// SkipV06, when true, disables the Photo Count validator.
	SkipV06 bool

	// SkipV07, when true, disables the Price Sanity validator.
	SkipV07 bool

	// SkipV08, when true, disables the Mileage Sanity validator.
	SkipV08 bool

	// SkipV09, when true, disables the Year Consistency validator.
	SkipV09 bool

	// SkipV10, when true, disables the Source URL Liveness validator.
	SkipV10 bool

	// ImageHeadTimeoutMs is the timeout for V05 HEAD requests per photo URL. Default: 3000 ms.
	ImageHeadTimeoutMs int

	// URLLivenessCacheTTLHours is the cache TTL for V10 source URL liveness checks. Default: 24 h.
	URLLivenessCacheTTLHours int
}

// Load builds a Config from environment variables.
func Load() (*Config, error) {
	c := &Config{
		DBPath:                   getEnv("QUALITY_DB_PATH", "./data/discovery.db"),
		MetricsAddr:              getEnv("QUALITY_METRICS_ADDR", ":9092"),
		BatchSize:                100,
		WorkerCount:              4,
		ImageHeadTimeoutMs:       3000,
		URLLivenessCacheTTLHours: 24,
	}

	if raw := os.Getenv("QUALITY_BATCH_SIZE"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: QUALITY_BATCH_SIZE must be a positive integer, got %q", raw)
		}
		c.BatchSize = n
	}

	if raw := os.Getenv("QUALITY_WORKERS"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: QUALITY_WORKERS must be a positive integer, got %q", raw)
		}
		c.WorkerCount = n
	}

	if os.Getenv("QUALITY_ONE_SHOT") == "true" {
		c.OneShot = true
	}
	if os.Getenv("QUALITY_SKIP_V01") == "true" {
		c.SkipV01 = true
	}
	if os.Getenv("QUALITY_SKIP_V02") == "true" {
		c.SkipV02 = true
	}
	if os.Getenv("QUALITY_SKIP_V03") == "true" {
		c.SkipV03 = true
	}
	if os.Getenv("QUALITY_SKIP_V04") == "true" {
		c.SkipV04 = true
	}
	if os.Getenv("QUALITY_SKIP_V05") == "true" {
		c.SkipV05 = true
	}
	if os.Getenv("QUALITY_SKIP_V06") == "true" {
		c.SkipV06 = true
	}
	if os.Getenv("QUALITY_SKIP_V07") == "true" {
		c.SkipV07 = true
	}
	if os.Getenv("QUALITY_SKIP_V08") == "true" {
		c.SkipV08 = true
	}
	if os.Getenv("QUALITY_SKIP_V09") == "true" {
		c.SkipV09 = true
	}
	if os.Getenv("QUALITY_SKIP_V10") == "true" {
		c.SkipV10 = true
	}

	if raw := os.Getenv("IMAGE_HEAD_TIMEOUT_MS"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: IMAGE_HEAD_TIMEOUT_MS must be a positive integer, got %q", raw)
		}
		c.ImageHeadTimeoutMs = n
	}

	if raw := os.Getenv("URL_LIVENESS_CACHE_TTL_HOURS"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: URL_LIVENESS_CACHE_TTL_HOURS must be a positive integer, got %q", raw)
		}
		c.URLLivenessCacheTTLHours = n
	}

	if raw := os.Getenv("QUALITY_COUNTRIES"); raw != "" {
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
