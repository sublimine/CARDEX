package config

import (
	"testing"
	"time"
)

func TestLoadDefaults(t *testing.T) {
	// Ensure a clean slate for the vars Load reads.
	for _, k := range []string{
		"PORT", "DATABASE_URL", "REDIS_ADDR", "LOG_LEVEL", "RATE_LIMIT_FREE",
		"RATE_LIMIT_PAID", "CACHE_TTL", "ALERT_EVAL_INTERVAL", "CHF_EUR_RATE", "ALERTS_ENABLED",
	} {
		t.Setenv(k, "")
	}

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Addr != ":8080" {
		t.Errorf("Addr = %q, want :8080", cfg.Addr)
	}
	if cfg.RateLimitFree != 100 || cfg.RateLimitPaid != 1000 {
		t.Errorf("rate limits = %d/%d, want 100/1000", cfg.RateLimitFree, cfg.RateLimitPaid)
	}
	if cfg.CacheTTL != 5*time.Minute {
		t.Errorf("CacheTTL = %s, want 5m", cfg.CacheTTL)
	}
	if !cfg.AlertsEnabled {
		t.Error("AlertsEnabled should default true")
	}
}

func TestLoadOverrides(t *testing.T) {
	t.Setenv("PORT", "9000")
	t.Setenv("RATE_LIMIT_FREE", "50")
	t.Setenv("CACHE_TTL", "30s")
	t.Setenv("CHF_EUR_RATE", "1.07")
	t.Setenv("ALERTS_ENABLED", "false")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Addr != ":9000" {
		t.Errorf("Addr = %q, want :9000", cfg.Addr)
	}
	if cfg.RateLimitFree != 50 {
		t.Errorf("RateLimitFree = %d, want 50", cfg.RateLimitFree)
	}
	if cfg.CacheTTL != 30*time.Second {
		t.Errorf("CacheTTL = %s, want 30s", cfg.CacheTTL)
	}
	if cfg.CHFtoEUR != 1.07 {
		t.Errorf("CHFtoEUR = %v, want 1.07", cfg.CHFtoEUR)
	}
	if cfg.AlertsEnabled {
		t.Error("AlertsEnabled should be false")
	}
}

func TestLoadRejectsInvalid(t *testing.T) {
	t.Setenv("LOG_LEVEL", "verbose")
	if _, err := Load(); err == nil {
		t.Error("expected error for invalid LOG_LEVEL")
	}
	t.Setenv("LOG_LEVEL", "info")
	t.Setenv("RATE_LIMIT_FREE", "notanumber")
	if _, err := Load(); err == nil {
		t.Error("expected error for invalid RATE_LIMIT_FREE")
	}
}
