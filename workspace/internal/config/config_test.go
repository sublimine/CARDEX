package config_test

import (
	"os"
	"testing"

	"cardex.eu/workspace/internal/config"
)

func TestLoadFromEnv_Defaults(t *testing.T) {
	clearEnv(t)

	cfg, err := config.LoadFromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != "8506" {
		t.Errorf("Port: got %q, want %q", cfg.Port, "8506")
	}
	if cfg.DBPath != "data/workspace.db" {
		t.Errorf("DBPath: got %q, want %q", cfg.DBPath, "data/workspace.db")
	}
	if cfg.MediaDir != "data/workspace/media" {
		t.Errorf("MediaDir: got %q, want %q", cfg.MediaDir, "data/workspace/media")
	}
	if cfg.NHTSABaseURL != "https://vpic.nhtsa.dot.gov" {
		t.Errorf("NHTSABaseURL: got %q", cfg.NHTSABaseURL)
	}
	if cfg.RDWBaseURL != "https://opendata.rdw.nl/resource" {
		t.Errorf("RDWBaseURL: got %q", cfg.RDWBaseURL)
	}
	if cfg.SMTP.Port != 25 {
		t.Errorf("SMTP.Port: got %d, want 25", cfg.SMTP.Port)
	}
	if cfg.MetricsAddr != ":9091" {
		t.Errorf("MetricsAddr: got %q, want %q", cfg.MetricsAddr, ":9091")
	}
}

func TestLoadFromEnv_OverrideAll(t *testing.T) {
	clearEnv(t)
	t.Setenv("WORKSPACE_PORT", "9000")
	t.Setenv("WORKSPACE_DB_PATH", "/tmp/ws.db")
	t.Setenv("WORKSPACE_MEDIA_DIR", "/tmp/media")
	t.Setenv("CARDEX_JWT_SECRET", "supersecret")
	t.Setenv("SMTP_HOST", "mail.example.com")
	t.Setenv("SMTP_PORT", "587")
	t.Setenv("SMTP_USER", "user@example.com")
	t.Setenv("SMTP_PASS", "pass")
	t.Setenv("SMTP_FROM", "noreply@example.com")
	t.Setenv("NHTSA_BASE_URL", "http://localhost:9999")
	t.Setenv("RDW_BASE_URL", "http://localhost:8888/resource")
	t.Setenv("WORKSPACE_METRICS_ADDR", ":9999")

	cfg, err := config.LoadFromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != "9000" {
		t.Errorf("Port: got %q", cfg.Port)
	}
	if cfg.JWTSecret != "supersecret" {
		t.Errorf("JWTSecret: got %q", cfg.JWTSecret)
	}
	if cfg.SMTP.Host != "mail.example.com" {
		t.Errorf("SMTP.Host: got %q", cfg.SMTP.Host)
	}
	if cfg.SMTP.Port != 587 {
		t.Errorf("SMTP.Port: got %d, want 587", cfg.SMTP.Port)
	}
	if cfg.NHTSABaseURL != "http://localhost:9999" {
		t.Errorf("NHTSABaseURL: got %q", cfg.NHTSABaseURL)
	}
}

func TestLoadFromEnv_InvalidSMTPPort(t *testing.T) {
	clearEnv(t)
	t.Setenv("SMTP_PORT", "not-a-number")

	_, err := config.LoadFromEnv()
	if err == nil {
		t.Fatal("expected error for invalid SMTP_PORT, got nil")
	}
}

func TestLoadFromEnv_SMTPPortOutOfRange(t *testing.T) {
	clearEnv(t)
	t.Setenv("SMTP_PORT", "99999")

	_, err := config.LoadFromEnv()
	if err == nil {
		t.Fatal("expected error for out-of-range SMTP_PORT, got nil")
	}
}

func TestValidate_Defaults(t *testing.T) {
	clearEnv(t)
	cfg, err := config.LoadFromEnv()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("Validate() on defaults returned error: %v", err)
	}
}

func TestValidate_MissingPort(t *testing.T) {
	cfg := &config.Config{
		DBPath:       "x.db",
		MediaDir:     "/media",
		NHTSABaseURL: "https://vpic.nhtsa.dot.gov",
		RDWBaseURL:   "https://opendata.rdw.nl/resource",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for empty Port")
	}
}

func TestSMTPConfigured(t *testing.T) {
	clearEnv(t)
	cfg, _ := config.LoadFromEnv()
	if cfg.SMTPConfigured() {
		t.Error("SMTPConfigured should be false with no env vars set")
	}

	t.Setenv("SMTP_HOST", "smtp.example.com")
	t.Setenv("SMTP_FROM", "noreply@example.com")
	cfg2, _ := config.LoadFromEnv()
	if !cfg2.SMTPConfigured() {
		t.Error("SMTPConfigured should be true when HOST and FROM are set")
	}
}

// clearEnv unsets all workspace config env vars for test isolation.
func clearEnv(t *testing.T) {
	t.Helper()
	vars := []string{
		"WORKSPACE_PORT", "WORKSPACE_DB_PATH", "WORKSPACE_MEDIA_DIR",
		"CARDEX_JWT_SECRET", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
		"SMTP_PASS", "SMTP_FROM", "NHTSA_BASE_URL", "RDW_BASE_URL",
		"WORKSPACE_METRICS_ADDR",
	}
	for _, v := range vars {
		t.Setenv(v, "") // t.Setenv restores on cleanup; setting to "" unsets effective value
		os.Unsetenv(v)
	}
}
