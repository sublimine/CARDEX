// Package config loads the API service configuration from environment variables.
//
// It follows the CARDEX house style: a hand-rolled loader (no viper/flags), env
// vars are UPPER_SNAKE, and Load returns (*Config, error) so the caller fails
// fast on invalid input. Defaults match docker-compose.yml's `api` service block.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config is the fully-resolved runtime configuration for the API service.
type Config struct {
	// Addr is the listen address, e.g. ":8080". Derived from PORT.
	Addr string
	// DatabaseURL is the PostgreSQL DSN (DATABASE_URL).
	DatabaseURL string
	// RedisAddr is host:port for Redis (REDIS_ADDR).
	RedisAddr string
	// RedisPassword authenticates to Redis (REDIS_PASSWORD).
	RedisPassword string
	// RedisDB is the Redis logical database index (REDIS_DB, default 0).
	RedisDB int
	// LogLevel is one of debug|info|warn|error (LOG_LEVEL, default info).
	LogLevel string
	// CORSOrigins is the allow-list of browser origins (CORS_ORIGINS, comma-separated).
	CORSOrigins []string

	// BootstrapKey is an optional admin/ops API key granted the highest tier without
	// a Redis entry (API_BOOTSTRAP_KEY). Empty disables the bootstrap key.
	BootstrapKey string

	// RateLimitFree / RateLimitPaid / RateLimitEnterprise are per-minute request
	// ceilings per tier (requests/min). Enterprise <= 0 means unlimited.
	RateLimitFree       int
	RateLimitPaid       int
	RateLimitEnterprise int

	// CacheTTL is how long market-price/arbitrage responses are cached in Redis.
	CacheTTL time.Duration
	// QueryTimeout bounds a single database query.
	QueryTimeout time.Duration

	// CHFtoEUR converts Swiss-franc prices to EUR for cross-country comparison
	// (CHF_EUR_RATE). Only used when a row's currency_raw is CHF and last_price_eur
	// is absent.
	CHFtoEUR float64

	// Alerts configuration.
	AlertsEnabled bool
	// AlertEvalInterval is how often the background evaluator scans active alerts.
	AlertEvalInterval time.Duration

	// SMTP settings for email alert delivery. If SMTPHost is empty, email delivery
	// is disabled (webhook delivery still works).
	SMTPHost string
	SMTPPort int
	SMTPUser string
	SMTPPass string
	SMTPFrom string
}

// Load reads the configuration from the process environment.
func Load() (*Config, error) {
	c := &Config{
		Addr:                ":" + getEnv("PORT", "8080"),
		DatabaseURL:         getEnv("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex"),
		RedisAddr:           getEnv("REDIS_ADDR", "localhost:6379"),
		RedisPassword:       os.Getenv("REDIS_PASSWORD"),
		LogLevel:            strings.ToLower(getEnv("LOG_LEVEL", "info")),
		BootstrapKey:        os.Getenv("API_BOOTSTRAP_KEY"),
		RateLimitFree:       100,
		RateLimitPaid:       1000,
		RateLimitEnterprise: 0,
		CacheTTL:            5 * time.Minute,
		QueryTimeout:        15 * time.Second,
		CHFtoEUR:            1.04,
		AlertsEnabled:       true,
		AlertEvalInterval:   15 * time.Minute,
		SMTPFrom:            getEnv("SMTP_FROM", "alerts@cardex.eu"),
	}

	c.CORSOrigins = splitCSV(getEnv("CORS_ORIGINS", "http://localhost:3001,http://localhost:3000"))

	if err := setInt(&c.RedisDB, "REDIS_DB", false); err != nil {
		return nil, err
	}
	if err := setInt(&c.RateLimitFree, "RATE_LIMIT_FREE", true); err != nil {
		return nil, err
	}
	if err := setInt(&c.RateLimitPaid, "RATE_LIMIT_PAID", true); err != nil {
		return nil, err
	}
	if err := setInt(&c.RateLimitEnterprise, "RATE_LIMIT_ENTERPRISE", false); err != nil {
		return nil, err
	}
	if err := setDuration(&c.CacheTTL, "CACHE_TTL"); err != nil {
		return nil, err
	}
	if err := setDuration(&c.QueryTimeout, "QUERY_TIMEOUT"); err != nil {
		return nil, err
	}
	if err := setDuration(&c.AlertEvalInterval, "ALERT_EVAL_INTERVAL"); err != nil {
		return nil, err
	}
	if err := setFloat(&c.CHFtoEUR, "CHF_EUR_RATE"); err != nil {
		return nil, err
	}

	if raw := os.Getenv("ALERTS_ENABLED"); raw != "" {
		c.AlertsEnabled = raw == "true" || raw == "1"
	}

	// SMTP (all optional).
	c.SMTPHost = os.Getenv("SMTP_HOST")
	c.SMTPUser = os.Getenv("SMTP_USER")
	c.SMTPPass = os.Getenv("SMTP_PASS")
	c.SMTPPort = 587
	if err := setInt(&c.SMTPPort, "SMTP_PORT", true); err != nil {
		return nil, err
	}

	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("config: DATABASE_URL is required")
	}
	if c.BootstrapKey != "" && len(c.BootstrapKey) < 16 {
		return nil, fmt.Errorf("config: API_BOOTSTRAP_KEY must be at least 16 characters (it grants enterprise access)")
	}
	switch c.LogLevel {
	case "debug", "info", "warn", "error":
	default:
		return nil, fmt.Errorf("config: LOG_LEVEL must be debug|info|warn|error, got %q", c.LogLevel)
	}

	return c, nil
}

// getEnv returns the env var value or a default when unset/empty.
func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// splitCSV trims and drops empties from a comma-separated list.
func splitCSV(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// setInt parses an optional integer env var into dst. When positive is true the
// value must be > 0.
func setInt(dst *int, key string, positive bool) error {
	raw := os.Getenv(key)
	if raw == "" {
		return nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return fmt.Errorf("config: %s must be an integer, got %q", key, raw)
	}
	if positive && n <= 0 {
		return fmt.Errorf("config: %s must be a positive integer, got %d", key, n)
	}
	*dst = n
	return nil
}

// setDuration parses an optional Go duration env var (e.g. "5m") into dst.
func setDuration(dst *time.Duration, key string) error {
	raw := os.Getenv(key)
	if raw == "" {
		return nil
	}
	d, err := time.ParseDuration(raw)
	if err != nil {
		return fmt.Errorf("config: %s must be a duration (e.g. 5m), got %q", key, raw)
	}
	if d <= 0 {
		return fmt.Errorf("config: %s must be positive, got %s", key, d)
	}
	*dst = d
	return nil
}

// setFloat parses an optional positive float env var into dst.
func setFloat(dst *float64, key string) error {
	raw := os.Getenv(key)
	if raw == "" {
		return nil
	}
	f, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return fmt.Errorf("config: %s must be a number, got %q", key, raw)
	}
	if f <= 0 {
		return fmt.Errorf("config: %s must be positive, got %v", key, f)
	}
	*dst = f
	return nil
}
