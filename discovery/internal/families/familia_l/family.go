// Package familia_l implements Family L — social profile discovery.
//
// Sprint 12 activates L.3 (YouTube) as the single live path. L.1 and L.2 are
// formal stubs with documented activation criteria.
//
// Sub-techniques:
//
//   - L.1 Google Maps Places (stub) — deferred: €50 budget constraint
//   - L.2 LinkedIn Company (stub)   — deferred: R1 zero-legal-risk policy
//   - L.3 YouTube channels (active) — YouTube Data API v3, requires YOUTUBE_API_KEY
//
// Country support: DE, FR, ES, NL, BE, CH for L.3.
// BaseWeights["L"] = 0.10.
package familia_l

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_l/googlemaps"
	"cardex.eu/discovery/internal/families/familia_l/linkedin"
	"cardex.eu/discovery/internal/families/familia_l/youtube"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "L"
	familyName = "Social profiles (YouTube active; Google Maps + LinkedIn deferred)"
)

// FamilyL orchestrates all L social-profile sub-techniques.
type FamilyL struct {
	googleMaps *googlemaps.GoogleMaps
	linkedIn   *linkedin.LinkedIn
	youTube    *youtube.YouTube
	log        *slog.Logger
}

// New constructs a FamilyL with production configuration.
// youTubeAPIKey is the YouTube Data API v3 key; pass "" to skip L.3.
func New(graph kg.KnowledgeGraph, youTubeAPIKey string) *FamilyL {
	return &FamilyL{
		googleMaps: googlemaps.New(graph),
		linkedIn:   linkedin.New(graph),
		youTube:    youtube.New(graph, youTubeAPIKey),
		log:        slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyL) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyL) Name() string { return familyName }

// Run executes all L sub-techniques for the given country.
func (f *FamilyL) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_l: sub-technique error",
				"sub", label, "country", country, "err", err)
		}
	}

	switch country {
	case "DE", "FR", "ES", "NL", "BE", "CH":
		// L.1: deferred stub (logs deferral reason)
		res1, err1 := f.googleMaps.Run(ctx, country)
		collect(res1, err1, "googlemaps")

		// L.2: deferred stub (logs deferral reason)
		res2, err2 := f.linkedIn.Run(ctx, country)
		collect(res2, err2, "linkedin")

		// L.3: active (skips gracefully if no API key)
		res3, err3 := f.youTube.Run(ctx, country)
		collect(res3, err3, "youtube")

	default:
		return result, fmt.Errorf("familia_l: unsupported country %q", country)
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
