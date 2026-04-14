// Package familia_h implements Family H — OEM dealer networks.
//
// Sprint 9 completes Family H by activating all 8 OEM dealer locators.
// Every locator uses browser.InterceptXHR + postcode geo-sweep, sharing
// the sweep and upsert logic from familia_h/common.
//
// Active OEM adapters (Sprint 9):
//
//   - H.VWG        — VW + Audi + Skoda + Seat           (4 brands × 6 countries)
//   - H.STELLANTIS — Peugeot + Citroën + DS + Opel + Fiat (5 brands × 6 countries)
//   - H.BMW        — BMW + MINI                           (2 brands × 6 countries)
//   - H.MERCEDES   — Mercedes-Benz                        (1 brand × 6 countries)
//   - H.TOYOTA     — Toyota + Lexus                       (2 brands × 6 countries)
//   - H.HYUNDAI    — Hyundai + Kia                        (2 brands × 6 countries)
//   - H.RENAULT    — Renault + Dacia + Alpine              (3 brands × 6 countries)
//   - H.FORD       — Ford                                  (1 brand × 6 countries)
//
// All OEMs are gracefully skipped when browser.Browser is nil (controlled by
// DISCOVERY_SKIP_BROWSER=true). Individual country combinations may be deferred
// if anti-bot measures are not bypassed at runtime; the adapter logs a warning
// and continues with remaining postcodes.
//
// Architecture notes:
//
//   - Stellantis and Renault share a similar backend API platform (both use
//     "dealerships" response envelope and identical field schemas). This suggests
//     they may share Capgemini/Inetum middleware — worth verifying for future
//     API key integration.
//
//   - Toyota wraps dealers in a result.dealers nested object (unique among the
//     8 OEMs); all others use flat envelope keys.
//
//   - BMW has the most aggressive anti-bot protection; Playwright's clean
//     Chromium fingerprint should bypass CDN checks, but may require additional
//     browser stealth options in Sprint 10 if 0 captures are observed in prod.
package familia_h

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/bmw"
	"cardex.eu/discovery/internal/families/familia_h/ford"
	"cardex.eu/discovery/internal/families/familia_h/hyundai"
	"cardex.eu/discovery/internal/families/familia_h/mercedes"
	"cardex.eu/discovery/internal/families/familia_h/renault"
	"cardex.eu/discovery/internal/families/familia_h/stellantis"
	"cardex.eu/discovery/internal/families/familia_h/toyota"
	"cardex.eu/discovery/internal/families/familia_h/vwg"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "H"
	familyName = "OEM dealer networks"
)

// OEMLocator is the interface each OEM adapter must implement.
type OEMLocator interface {
	// OEMID returns the OEM brand group identifier (e.g. "VWG", "BMW", "TOYOTA").
	OEMID() string

	// Run sweeps the dealer locator for the given country and upserts results
	// into the KG.
	Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error)
}

// OEMConfig holds per-OEM configuration for environment-based overrides.
type OEMConfig struct {
	OEMID     string
	Countries []string
	BaseURL   string
	APIKey    string
}

// FamilyH orchestrates all H OEM dealer locator sub-techniques.
type FamilyH struct {
	locators map[string]OEMLocator // oemID → locator
	log      *slog.Logger
}

// New constructs a FamilyH and registers all 8 OEM locators.
// b may be nil — every locator skips gracefully when the browser is absent.
func New(graph kg.KnowledgeGraph, b browser.Browser) *FamilyH {
	f := &FamilyH{
		locators: make(map[string]OEMLocator, 8),
		log:      slog.Default().With("family", familyID),
	}

	for _, loc := range []OEMLocator{
		vwg.New(graph, b),
		stellantis.New(graph, b),
		bmw.New(graph, b),
		mercedes.New(graph, b),
		toyota.New(graph, b),
		hyundai.New(graph, b),
		renault.New(graph, b),
		ford.New(graph, b),
	} {
		f.locators[loc.OEMID()] = loc
	}

	return f
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyH) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyH) Name() string { return familyName }

// Run executes all registered OEM locators for the given country.
func (f *FamilyH) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	for _, loc := range f.locators {
		if ctx.Err() != nil {
			break
		}
		res, err := loc.Run(ctx, country)
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_h: OEM locator error",
				"oem", loc.OEMID(),
				"country", country,
				"err", err,
			)
		}
	}

	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return result, nil
}

// HealthCheck returns nil — no external endpoints to probe (all OEMs
// are SPA-based; health is implicitly tested during Run).
func (f *FamilyH) HealthCheck(_ context.Context) error {
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}

// RegisterLocator adds (or replaces) an OEMLocator at runtime.
// Useful for integration tests and future OEM additions.
func (f *FamilyH) RegisterLocator(loc OEMLocator) {
	f.locators[loc.OEMID()] = loc
}

// Locators returns a snapshot of the registered locator map.
func (f *FamilyH) Locators() map[string]OEMLocator {
	out := make(map[string]OEMLocator, len(f.locators))
	for k, v := range f.locators {
		out[k] = v
	}
	return out
}
