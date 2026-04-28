// Package familia_o implements Family O -- press archives and event signals.
//
// Family O extracts automotive dealer signals from press archives and trade
// news feeds. Unlike Families A-N which discover dealers structurally (registry
// data, geo data, web presence), O discovers events -- openings, closings,
// mergers, sales -- that cross-validate and timestamp existing KG entities.
//
// Sub-techniques Sprint 14:
//
//   - O.1 GDELT Project: free worldwide news search, NER on article text,
//     cross-validation against KG, LOW_CONFIDENCE candidate creation
//   - O.2 RSS/Atom monitoring: curated automotive trade feeds per country,
//     NER on item titles, same cross-validation pipeline as O.1
//   - O.3 Wayback Monitor: DEFERRED -- requires Phase 3 extraction pipeline
//
// BaseWeights["O"] = 0.05 -- press signals are qualitative event evidence;
// they supplement but do not drive dealer discovery.
//
// Execution order: O.1 then O.2. O.3 is a no-op stub.
package familia_o

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_o/gdelt"
	"cardex.eu/discovery/internal/families/familia_o/rss"
	"cardex.eu/discovery/internal/families/familia_o/wayback_monitor"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "O"
	familyName = "Press archives and event signals"
)

// FamilyO orchestrates all O press archive sub-techniques.
type FamilyO struct {
	gdelt   *gdelt.GDELT
	rss     *rss.RSSPoller
	wayback *wayback_monitor.WaybackMonitor
	log     *slog.Logger
}

// New constructs a FamilyO with production configuration.
func New(graph kg.KnowledgeGraph) *FamilyO {
	return &FamilyO{
		gdelt:   gdelt.New(graph),
		rss:     rss.New(graph),
		wayback: wayback_monitor.New(graph),
		log:     slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyO) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyO) Name() string { return familyName }

// Run executes O.1, O.2, and O.3 sub-techniques for the given country.
func (f *FamilyO) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_o: sub-technique error",
				"sub", label, "country", country, "err", err)
		}
	}

	// O.1 GDELT -- worldwide press archive
	res1, err1 := f.gdelt.Run(ctx, country)
	collect(res1, err1, "gdelt")

	// O.2 RSS feeds -- trade news monitoring
	if ctx.Err() == nil {
		res2, err2 := f.rss.Run(ctx, country)
		collect(res2, err2, "rss")
	}

	// O.3 Wayback Monitor -- deferred stub
	if ctx.Err() == nil {
		res3, err3 := f.wayback.Run(ctx, country)
		collect(res3, err3, "wayback_monitor")
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

// HealthCheck satisfies the runner.FamilyRunner interface.
func (f *FamilyO) HealthCheck(_ context.Context) error {
	return fmt.Errorf("familia_o: HealthCheck not implemented -- O.1 GDELT is unauthenticated; O.2 feeds are polled lazily")
}
