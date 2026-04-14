// Package familia_m implements Family M — Fiscal signals & VAT validation.
//
// Sprint 11 activates two VAT validation sub-techniques:
//
//   - M.1 VIES VAT validation batch (EU: DE/FR/ES/BE/NL)
//   - M.2 Swiss UID-Register validation (CH) via SOAP
//
// Deferred (Sprint 12+):
//
//   - M.3 Job board signals — Indeed/Stepstone/InfoJobs/Monster scraping
//     requires Playwright stealth mode extensions not yet available.
//
// # Architecture note
//
// Family M is an enrichment family, not a primary discovery family.
// BaseWeights["M"] = 0.0 — M does NOT add new dealer entities; it validates
// and enriches existing ones discovered by Families A/B/G/H.
//
// The confidence bump (+0.10) applied when VIES/UID confirms a valid, name-matching
// VAT registration is a delta on the existing confidence_score, not a base weight.
//
// M.Run() is designed to be called AFTER Families A/B/G/H have completed at least
// one discovery cycle, so that the dealer_entity table is populated.
//
// Country → sub-technique mapping:
//
//	DE, FR, ES, BE, NL → M.1 (VIES EU VAT)
//	CH                 → M.2 (UID-Register SOAP)
//	all                → M.3 (deferred)
package familia_m

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_m/ch_uid"
	"cardex.eu/discovery/internal/families/familia_m/jobboards"
	"cardex.eu/discovery/internal/families/familia_m/vies"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "M"
	familyName = "Fiscal signals & VAT validation"
)

// FamilyM orchestrates all M enrichment sub-techniques.
type FamilyM struct {
	vies      *vies.VIES
	chUID     *ch_uid.ChUID
	jobBoards *jobboards.JobBoards
	log       *slog.Logger
}

// New constructs a FamilyM with production endpoints.
func New(graph kg.KnowledgeGraph) *FamilyM {
	return &FamilyM{
		vies:      vies.New(graph),
		chUID:     ch_uid.New(graph),
		jobBoards: jobboards.New(graph),
		log:       slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyM) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyM) Name() string { return familyName }

// Run executes the appropriate M sub-techniques for the given country.
// For VIES (M.1), a single batch run covers all EU countries simultaneously —
// when country is "DE", "FR", "ES", "BE", or "NL" the full EU VAT batch runs.
// The batch is idempotent (stale-day guard prevents re-validation within 30 days).
func (f *FamilyM) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_m: sub-technique error", "sub", label, "country", country, "err", err)
		}
	}

	switch country {
	case "DE", "FR", "ES", "BE", "NL":
		// M.1: EU VIES batch (runs once for any EU country; internal dedup by staleDays).
		res, err := f.vies.Run(ctx)
		collect(res, err, "vies")
		// M.3 deferred
		res2, err2 := f.jobBoards.Run(ctx, country)
		collect(res2, err2, "jobboards")

	case "CH":
		// M.2: Swiss UID-Register
		res, err := f.chUID.Run(ctx)
		collect(res, err, "ch_uid")
		// M.3 deferred
		res2, err2 := f.jobBoards.Run(ctx, country)
		collect(res2, err2, "jobboards")

	default:
		return result, fmt.Errorf("familia_m: unsupported country %q", country)
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

// HealthCheck verifies the VIES endpoint is reachable.
func (f *FamilyM) HealthCheck(ctx context.Context) error {
	// Probe VIES with a dummy request to check connectivity.
	// We use a known-valid format with a fake VAT — the HTTP endpoint should
	// respond with isValid=false, not a network error.
	_, err := f.vies.ValidateVAT(ctx, "FR", "00000000000")
	if err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_m health: VIES: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
