// Package familia_e implements Family E -- DMS hosted infrastructure mapping.
//
// Family E detects and maps the DMS (Dealer Management System) software and
// hosting infrastructure used by EU automotive dealers. DMS providers host
// tens of thousands of dealer websites on shared infrastructure, making DMS
// fingerprinting a high-yield signal for:
//
//   - Identifying dealer web presences not otherwise discoverable (directory mining)
//   - Cross-validating dealer identities across different data sources
//   - Understanding market share of DMS vendors per country
//
// Sub-techniques Sprint 14:
//
//   - E.1 Extended EU DMS fingerprinting: promotes D.3 hints + runs extended
//     fingerprint scans for CDK, Reynolds, incadea, Modix, Carmen, AutoLine,
//     DealerSocket, iCar, Brain Solutions
//   - E.2 DMS directory mining: DEFERRED -- CDK/incadea portals require JS rendering
//   - E.3 DMS IP clustering: propagates known DMS providers to co-hosted dealers
//     using Censys/Shodan host IP clusters from Familia N
//
// Execution order: E.1 → E.2 (no-op stub) → E.3.
// E.3 benefits from E.1 having already set dms_provider on fingerprinted presences,
// so ordering matters.
//
// BaseWeights["E"] = 0.05 -- DMS infrastructure is a secondary validation signal,
// not a primary discovery channel.
package familia_e

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_e/directory_mining"
	"cardex.eu/discovery/internal/families/familia_e/dms_fingerprinter"
	"cardex.eu/discovery/internal/families/familia_e/ip_cluster"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "E"
	familyName = "DMS hosted infrastructure mapping"
)

// FamilyE orchestrates all E DMS infrastructure sub-techniques.
type FamilyE struct {
	fingerprinter  *dms_fingerprinter.DMSFingerprinter
	directoryMiner *directory_mining.DirectoryMiner
	ipClusterer    *ip_cluster.IPClusterer
	log            *slog.Logger
}

// New constructs a FamilyE with production configuration.
func New(graph kg.KnowledgeGraph) *FamilyE {
	return &FamilyE{
		fingerprinter:  dms_fingerprinter.New(graph),
		directoryMiner: directory_mining.New(graph),
		ipClusterer:    ip_cluster.New(graph),
		log:            slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyE) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyE) Name() string { return familyName }

// Run executes E.1, E.2 (stub), and E.3 sub-techniques for the given country.
func (f *FamilyE) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_e: sub-technique error",
				"sub", label, "country", country, "err", err)
		}
	}

	// E.1 -- extended DMS fingerprinting (promotes D.3 hints + new scans)
	res1, err1 := f.fingerprinter.Run(ctx, country)
	collect(res1, err1, "dms_fingerprinter")

	// E.2 -- DMS directory mining (deferred stub)
	if ctx.Err() == nil {
		res2, err2 := f.directoryMiner.Run(ctx, country)
		collect(res2, err2, "directory_mining")
	}

	// E.3 -- DMS IP clustering (propagates E.1 results to co-hosted dealers)
	// Run after E.1 so newly fingerprinted providers are available for propagation.
	if ctx.Err() == nil {
		res3, err3 := f.ipClusterer.Run(ctx, country)
		collect(res3, err3, "ip_cluster")
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
func (f *FamilyE) HealthCheck(_ context.Context) error {
	return fmt.Errorf("familia_e: HealthCheck not implemented -- E.1 uses no external auth; E.3 is KG-local only")
}
