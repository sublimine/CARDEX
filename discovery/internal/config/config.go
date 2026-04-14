// Package config loads runtime configuration from environment variables.
// No configuration files — 12-factor style.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
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
	// Required for Family A FR sub-technique.
	InseeToken string

	// InseeRatePerMin is the number of requests per minute allowed against
	// the INSEE Sirene API. Defaults to 25 (below the 30 req/min free-tier limit).
	InseeRatePerMin int

	// OffeneRegisterDBPath is the filesystem path where the decompressed
	// OffeneRegister SQLite will be stored.
	// Default: ./data/offeneregister.db
	OffeneRegisterDBPath string

	// KvKAPIKey is the API key for the KvK Zoeken v2 API (Path 2 of A.NL.1).
	// If empty, keyword search is skipped; bulk density ingest still runs.
	KvKAPIKey string

	// KBOUser and KBOPass are the KBO Open Data portal credentials.
	// Required for A.BE.1. Register at kbopub.economie.fgov.be/kbo-open-data.
	KBOUser string
	KBOPass string

	// OneShot, when true, runs a single discovery cycle and exits.
	// Default: false (daemon mode — blocks until SIGINT/SIGTERM).
	OneShot bool

	// Countries is the list of ISO-3166-1 alpha-2 codes to run discovery for.
	// Default: ["FR"]
	Countries []string
}

// LoadFromEnv builds a Config from environment variables.
// Returns an error if any required variable has an invalid value.
func LoadFromEnv() (*Config, error) {
	c := &Config{
		DBPath:               getEnvDefault("DISCOVERY_DB_PATH", "./data/discovery.db"),
		MetricsAddr:          getEnvDefault("METRICS_ADDR", ":9090"),
		InseeToken:           os.Getenv("INSEE_TOKEN"),
		InseeRatePerMin:      25,
		OffeneRegisterDBPath: getEnvDefault("OFFENEREGISTER_DB_PATH", "./data/offeneregister.db"),
		KvKAPIKey:            os.Getenv("KVK_API_KEY"),
		KBOUser:              os.Getenv("KBO_USER"),
		KBOPass:              os.Getenv("KBO_PASS"),
		Countries:            []string{"FR"},
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

	if raw := os.Getenv("DISCOVERY_COUNTRIES"); raw != "" {
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

func getEnvDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
