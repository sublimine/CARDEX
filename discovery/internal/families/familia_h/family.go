// Package familia_h implements Family H — OEM dealer networks.
//
// Sprint 8 activates H.VWG — Volkswagen Group dealer locator (VW + Audi +
// Skoda + Seat × DE/FR/ES/NL/BE/CH) using browser.InterceptXHR geo-sweep
// delivered in Sprint 7.
//
// Other OEM adapters remain deferred:
//
//   - H.STELLANTIS — Peugeot + Citroën + DS + Opel + Fiat
//     Reason: peugeot.de robots.txt returns HTTP 403 (blocked for bots).
//
//   - H.BMW    — BMW Group (BMW + MINI)
//     Reason: bmw.de robots.txt / locator page both timeout (DDoS protection).
//
//   - H.MERCEDES — Mercedes-Benz Group
//     Reason: mercedes-benz.de robots.txt timeout (same DDoS-protection pattern).
//
//   - H.TOYOTA  — Toyota + Lexus
//     Reason: robots.txt explicitly: Disallow: *?dealer=* / *?dealerId=*
//     Dealer API returns HTTP 403.
//
//   - H.HYUNDAI — Hyundai + Kia
//     Reason: TLS certificate error on robots.txt endpoint.
//
//   - H.RENAULT — Renault + Dacia + Alpine
//     Reason: robots.txt explicitly: Disallow: *dealerId=*
//
//   - H.FORD   — Ford
//     Reason: ford.de consistently times out (CDN / bot-protection).
//
// Country → sub-technique mapping (Sprint 8):
//
//	DE, FR, ES, NL, BE, CH → H.VWG (VW + Audi + Skoda + Seat)
package familia_h

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/browser"
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

// OEMConfig holds per-OEM configuration. Populated from environment variables
// or config struct when the OEM adapter is implemented.
type OEMConfig struct {
	// OEMID is the brand group identifier (e.g. "VWG", "BMW").
	OEMID string

	// Countries is the list of ISO-3166-1 alpha-2 codes to sweep.
	Countries []string

	// BaseURL overrides the production dealer locator endpoint (for tests).
	BaseURL string

	// APIKey is the optional API key for OEMs that provide authenticated dealer APIs.
	APIKey string
}

// FamilyH orchestrates OEM dealer locator sub-techniques.
type FamilyH struct {
	locators map[string]OEMLocator // oemID → locator
	log      *slog.Logger
}

// New constructs a FamilyH and registers the VWG locator.
// b may be nil — the VWG locator (and all browser-dependent OEM sub-techniques)
// will skip gracefully when browser is not initialised.
func New(graph kg.KnowledgeGraph, b browser.Browser) *FamilyH {
	f := &FamilyH{
		locators: make(map[string]OEMLocator),
		log:      slog.Default().With("family", familyID),
	}

	vwgLoc := vwg.New(graph, b)
	f.locators[vwgLoc.OEMID()] = vwgLoc

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

	if len(f.locators) == 0 {
		f.log.Info("familia_h: no OEM locators registered",
			"country", country,
		)
	}

	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return result, nil
}

// HealthCheck returns nil when all locators are healthy.
// In Sprint 8 only VWG is active and it has no external health-check endpoint.
func (f *FamilyH) HealthCheck(_ context.Context) error {
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}

// RegisterLocator adds an OEMLocator to the family at runtime.
// Used by tests and future sprint integrations.
func (f *FamilyH) RegisterLocator(loc OEMLocator) {
	f.locators[loc.OEMID()] = loc
}

// Locators returns a copy of the registered locator map (for testing / introspection).
func (f *FamilyH) Locators() map[string]OEMLocator {
	out := make(map[string]OEMLocator, len(f.locators))
	for k, v := range f.locators {
		out[k] = v
	}
	return out
}

// deferred OEM list for informational logging.
var deferredOEMs = []string{
	"STELLANTIS", "BMW", "MERCEDES", "TOYOTA", "HYUNDAI", "RENAULT", "FORD",
}

// DeferredOEMs returns the list of OEM IDs not yet implemented in Sprint 8.
func DeferredOEMs() []string { return deferredOEMs }

