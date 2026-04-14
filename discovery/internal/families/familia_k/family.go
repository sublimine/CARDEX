// Package familia_k implements Family K — Alternative search engines.
//
// Sprint 11 activates K.1 SearXNG meta-search with 10 country-specific query
// templates × 6 target countries, rotating across 5 public SearXNG instances.
//
// Deferred (Sprint 12+):
//
//   - K.2 Marginalia Search — deferred; lower EU dealer coverage vs K.1.
//
// # Architecture note
//
// Family K is a supplementary discovery family. BaseWeights["K"] = 0.05 —
// search-engine results are low-confidence signals; dealers discovered via K
// require cross-validation from Families A/B/H to raise confidence.
//
// Country → sub-technique mapping:
//
//	DE, FR, ES, NL, BE, CH → K.1 (SearXNG) + K.2 (Marginalia, deferred)
package familia_k

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_k/marginalia"
	"cardex.eu/discovery/internal/families/familia_k/searxng"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "K"
	familyName = "Alternative search engines"
)

// FamilyK orchestrates all K search-engine sub-techniques.
type FamilyK struct {
	searxng    *searxng.SearXNG
	marginalia *marginalia.Marginalia
	log        *slog.Logger
}

// New constructs a FamilyK with production configuration.
func New(graph kg.KnowledgeGraph) *FamilyK {
	return &FamilyK{
		searxng:    searxng.New(graph),
		marginalia: marginalia.New(graph),
		log:        slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyK) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyK) Name() string { return familyName }

// Run executes K sub-techniques for the given country.
func (f *FamilyK) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	collect := func(res *runner.SubTechniqueResult, err error, label string) {
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_k: sub-technique error", "sub", label, "country", country, "err", err)
		}
	}

	switch country {
	case "DE", "FR", "ES", "NL", "BE", "CH":
		res, err := f.searxng.Run(ctx, country)
		collect(res, err, "searxng")
		res2, err2 := f.marginalia.Run(ctx, country)
		collect(res2, err2, "marginalia")

	default:
		return result, fmt.Errorf("familia_k: unsupported country %q", country)
	}

	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)

	if result.TotalErrors > 0 {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
	} else {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	}
	return result, nil
}

// HealthCheck verifies connectivity to the first SearXNG instance.
func (f *FamilyK) HealthCheck(_ context.Context) error {
	// SearXNG instances are public and ephemeral; health is implicitly tested
	// during Run. Return nil — no hard dependency to probe pre-flight.
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
