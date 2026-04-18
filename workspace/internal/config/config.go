// Package config loads workspace service runtime configuration from environment
// variables. No configuration files — 12-factor style.
package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds all runtime configuration for the workspace service.
type Config struct {
	// Port is the TCP port the HTTP server listens on.
	// Env: WORKSPACE_PORT. Default: 8506.
	Port string

	// DBPath is the filesystem path for the shared SQLite database.
	// Env: WORKSPACE_DB_PATH. Default: data/workspace.db.
	DBPath string

	// MediaDir is the root directory for stored vehicle media files.
	// Env: WORKSPACE_MEDIA_DIR. Default: data/workspace/media.
	MediaDir string

	// JWTSecret is the HMAC-SHA256 signing key for JWT tokens.
	// Env: CARDEX_JWT_SECRET. Required in production; an ephemeral random
	// value is used when absent (all tokens invalidated on restart).
	JWTSecret string

	// SMTP holds outbound email configuration for the reply engine.
	SMTP SMTPConfig

	// NHTSABaseURL is the base URL for the NHTSA vPIC public API.
	// Env: NHTSA_BASE_URL. Default: https://vpic.nhtsa.dot.gov.
	NHTSABaseURL string

	// RDWBaseURL is the base URL for the Dutch RDW open data API (Socrata).
	// Env: RDW_BASE_URL. Default: https://opendata.rdw.nl/resource.
	RDWBaseURL string

	// MetricsAddr is the address for the Prometheus /metrics HTTP server.
	// Env: WORKSPACE_METRICS_ADDR. Default: :9091.
	MetricsAddr string
}

// SMTPConfig holds outbound SMTP configuration.
type SMTPConfig struct {
	Host string
	Port int
	User string
	Pass string
	From string
}

// LoadFromEnv reads configuration from environment variables, applying
// defaults for optional fields.
func LoadFromEnv() (*Config, error) {
	smtpPort := 25
	if raw := os.Getenv("SMTP_PORT"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n <= 0 || n > 65535 {
			return nil, fmt.Errorf("config: SMTP_PORT must be a valid port number, got %q", raw)
		}
		smtpPort = n
	}

	c := &Config{
		Port:         envDefault("WORKSPACE_PORT", "8506"),
		DBPath:       envDefault("WORKSPACE_DB_PATH", "data/workspace.db"),
		MediaDir:     envDefault("WORKSPACE_MEDIA_DIR", "data/workspace/media"),
		JWTSecret:    os.Getenv("CARDEX_JWT_SECRET"),
		NHTSABaseURL: envDefault("NHTSA_BASE_URL", "https://vpic.nhtsa.dot.gov"),
		RDWBaseURL:   envDefault("RDW_BASE_URL", "https://opendata.rdw.nl/resource"),
		MetricsAddr:  envDefault("WORKSPACE_METRICS_ADDR", ":9091"),
		SMTP: SMTPConfig{
			Host: os.Getenv("SMTP_HOST"),
			Port: smtpPort,
			User: os.Getenv("SMTP_USER"),
			Pass: os.Getenv("SMTP_PASS"),
			From: os.Getenv("SMTP_FROM"),
		},
	}

	return c, nil
}

// Validate returns an error if the configuration is invalid for production use.
// JWTSecret absence is a warning condition — the caller is responsible for
// generating an ephemeral secret and logging the warning.
func (c *Config) Validate() error {
	if c.Port == "" {
		return fmt.Errorf("config: WORKSPACE_PORT must not be empty")
	}
	if c.DBPath == "" {
		return fmt.Errorf("config: WORKSPACE_DB_PATH must not be empty")
	}
	if c.MediaDir == "" {
		return fmt.Errorf("config: WORKSPACE_MEDIA_DIR must not be empty")
	}
	if c.NHTSABaseURL == "" {
		return fmt.Errorf("config: NHTSA_BASE_URL must not be empty")
	}
	if c.RDWBaseURL == "" {
		return fmt.Errorf("config: RDW_BASE_URL must not be empty")
	}
	return nil
}

// SMTPConfigured reports whether enough SMTP fields are set to send email.
func (c *Config) SMTPConfigured() bool {
	return c.SMTP.Host != "" && c.SMTP.From != ""
}

func envDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
