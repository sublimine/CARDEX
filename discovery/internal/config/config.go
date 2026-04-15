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

	// SkipFamilyC, when true, bypasses Familia C (web cartography) entirely.
	// Useful when CT/Wayback/DNS rate limits need to be preserved.
	// Default: false
	SkipFamilyC bool

	// SkipFamilyF, when true, bypasses Familia F (aggregator directories) entirely.
	// Useful when marketplace crawl rate limits need to be preserved.
	// Default: false
	SkipFamilyF bool

	// SkipFamilyG, when true, bypasses Familia G (sectoral associations) entirely.
	// Default: false
	SkipFamilyG bool

	// SkipFamilyH, when true, bypasses Familia H (OEM dealer networks) entirely.
	// Default: false
	SkipFamilyH bool

	// SkipFamilyK, when true, bypasses Familia K (alternative search engines) entirely.
	// Useful when SearXNG query budget needs to be preserved.
	// Default: false
	SkipFamilyK bool

	// SkipFamilyM, when true, bypasses Familia M (fiscal signal enrichment) entirely.
	// Useful when VAT validation rate limits need to be preserved.
	// Default: false
	SkipFamilyM bool

	// SkipFamilyI, when true, bypasses Familia I (inspection & certification) entirely.
	// Useful when external API rate limits for Open Data endpoints need to be preserved.
	// Default: false
	SkipFamilyI bool

	// SkipFamilyD, when true, bypasses Familia D (CMS fingerprinting) entirely.
	// Useful when crawl rate limits for dealer homepages need to be preserved.
	// Default: false
	SkipFamilyD bool

	// SkipFamilyL, when true, bypasses Familia L (social profiles) entirely.
	// Default: false
	SkipFamilyL bool

	// YouTubeAPIKey is the YouTube Data API v3 key used by L.3.
	// When empty, L.3 is silently skipped (no error).
	// Obtain a free key at console.cloud.google.com -> APIs & Services -> YouTube Data API v3.
	YouTubeAPIKey string

	// SkipFamilyJ, when true, bypasses Familia J (sub-jurisdiction registries) entirely.
	// Useful when Pappers.fr rate limits need to be preserved.
	// Default: false
	SkipFamilyJ bool

	// PappersAPIKey is the Pappers.fr API token used by J.FR.1.
	// When empty, unauthenticated calls are made (rate limit: 50 req/h).
	// Obtain at pappers.fr/api.
	PappersAPIKey string

	// SkipFamilyN, when true, bypasses Familia N (infrastructure intelligence) entirely.
	// Useful when Censys/Shodan/ViewDNS rate limits need to be preserved.
	// Default: false
	SkipFamilyN bool

	// CensysAPIID and CensysAPISecret are the Censys v2 API credentials used by N.1.
	// When either is empty, N.1 is silently skipped.
	// Obtain at censys.io -> Account -> API Access.
	CensysAPIID     string
	CensysAPISecret string

	// ShodanAPIKey is the Shodan API key used by N.2.
	// When empty, N.2 is silently skipped.
	// Obtain at account.shodan.io.
	ShodanAPIKey string

	// ViewDNSAPIKey is the ViewDNS.info API key used by N.4.
	// When empty, N.4 is silently skipped.
	// Obtain at viewdns.info/api.
	ViewDNSAPIKey string

	// SkipBrowser, when true, skips browser (Playwright) initialisation.
	// All browser-dependent sub-techniques (F.2, G.FR.1, H.VWG) will be silently
	// skipped. Useful in CI environments without Playwright installed.
	// Default: false
	SkipBrowser bool
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

	if os.Getenv("DISCOVERY_SKIP_FAMILY_C") == "true" {
		c.SkipFamilyC = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_F") == "true" {
		c.SkipFamilyF = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_G") == "true" {
		c.SkipFamilyG = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_H") == "true" {
		c.SkipFamilyH = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_I") == "true" {
		c.SkipFamilyI = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_K") == "true" {
		c.SkipFamilyK = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_M") == "true" {
		c.SkipFamilyM = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_D") == "true" {
		c.SkipFamilyD = true
	}

	if os.Getenv("DISCOVERY_SKIP_FAMILY_L") == "true" {
		c.SkipFamilyL = true
	}

	c.YouTubeAPIKey = os.Getenv("YOUTUBE_API_KEY")

	if os.Getenv("DISCOVERY_SKIP_FAMILY_J") == "true" {
		c.SkipFamilyJ = true
	}
	c.PappersAPIKey = os.Getenv("PAPPERS_API_KEY")

	if os.Getenv("DISCOVERY_SKIP_FAMILY_N") == "true" {
		c.SkipFamilyN = true
	}
	c.CensysAPIID = os.Getenv("CENSYS_API_ID")
	c.CensysAPISecret = os.Getenv("CENSYS_API_SECRET")
	c.ShodanAPIKey = os.Getenv("SHODAN_API_KEY")
	c.ViewDNSAPIKey = os.Getenv("VIEWDNS_API_KEY")

	if os.Getenv("DISCOVERY_SKIP_BROWSER") == "true" {
		c.SkipBrowser = true
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
