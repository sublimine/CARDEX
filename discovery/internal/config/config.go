// Package config loads runtime configuration from environment variables.
// No configuration files — 12-factor style.
package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds all runtime configuration for the discovery service.
type Config struct {
	// DBPath is the filesystem path for the SQLite KG database.
	// Default: ./data/discovery.db
	DBPath string

	// MetricsAddr is the address for the Prometheus /metrics HTTP server.
	// Default: :9090
	MetricsAddr string

	// InseeToken is the OAuth2 Bearer token for the INSEE Sirene API.
	// Required for Family A FR sub-techniques.
	InseeToken string

	// InseeRatePerMin is the number of requests per minute allowed against
	// the INSEE Sirene API. Defaults to 25 (conservative below the 30 req/min
	// free-tier limit).
	InseeRatePerMin int

	// OneShot, when true, runs a single discovery cycle and exits.
	// Default: false (continuous daemon mode).
	OneShot bool

	// Countries is the comma-separated list of ISO-3166-1 codes to discover.
	// Default: "FR"
	Countries []string
}

// LoadFromEnv builds a Config from environment variables.
// Returns an error if any required variable is absent.
func LoadFromEnv() (*Config, error) {
	c := &Config{
		DBPath:          getEnvDefault("DISCOVERY_DB_PATH", "./data/discovery.db"),
		MetricsAddr:     getEnvDefault("METRICS_ADDR", ":9090"),
		InseeToken:      os.Getenv("INSEE_TOKEN"),
		InseeRatePerMin: 25,
		Countries:       []string{"FR"},
	}

	if raw := os.Getenv("INSEE_RATE_PER_MIN"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 {
			return nil, fmt.Errorf("config: INSEE_RATE_PER_MIN must be a positive integer, got %q", raw)
		}
		c.InseeRatePerMin = n
	}

	if os.Getenv("DISCOVERY_ONE_SHOT") == "true" {
		c.OneShot = true
	}

	return c, nil
}

func getEnvDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
