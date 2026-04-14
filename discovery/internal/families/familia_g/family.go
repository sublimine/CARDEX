// Package familia_g implements Family G — Asociaciones sectoriales.
//
// Sprint 8 activates G.FR.1 Mobilians using the Playwright browser module
// delivered in Sprint 7.
//
// Active sub-techniques:
//
//   - G.NL.1 — BOVAG member directory (NL)
//   - G.FR.1 — Mobilians (ex-CNPA umbrella) member directory (FR)
//
// Deferred:
//
//   - G.DE.1 — ZDK Zentralverband Deutsches Kraftfahrzeuggewerbe
//     Reason: member directory at kfzgewerbe.de/mitglieder/ is behind a TYPO3
//     login wall (tx_felogin_login). No public member listing found.
//
//   - G.ES.1 — FACONAUTO
//     Reason: no public dealer member directory found.
//
//   - G.BE.1 — TRAXIO (Belgium)
//     Reason: no accessible member directory URL found on the public site.
//
//   - G.CH.1 — AGVS-UPSA (Auto Gewerbe Verband Schweiz)
//     Reason: robots.txt explicitly blocks Solr search parameter paths.
//
// Country → sub-technique mapping:
//
//	NL → G.NL.1 (BOVAG)
//	FR → G.FR.1 (Mobilians)
//	DE, ES, BE, CH → no source; logged and skipped
package familia_g

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_g/bovag"
	"cardex.eu/discovery/internal/families/familia_g/mobilians"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "G"
	familyName = "Asociaciones sectoriales"
)

// FamilyG orchestrates the implemented G sub-techniques per country.
type FamilyG struct {
	bovag     *bovag.BOVAG
	mobilians *mobilians.Mobilians
	log       *slog.Logger
}

// New constructs a FamilyG with production endpoints.
func New(graph kg.KnowledgeGraph, b browser.Browser) *FamilyG {
	return &FamilyG{
		bovag:     bovag.New(graph),
		mobilians: mobilians.New(graph, b),
		log:       slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyG) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyG) Name() string { return familyName }

// Run executes the configured G sub-techniques for the given country.
func (f *FamilyG) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	switch country {
	case "NL":
		res, err := f.bovag.Run(ctx)
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_g: BOVAG error", "err", err)
		}

	case "FR":
		res, err := f.mobilians.Run(ctx)
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_g: Mobilians error", "err", err)
		}

	case "DE":
		f.log.Info("familia_g: G.DE.1 ZDK deferred",
			"country", country,
			"reason", "member directory behind TYPO3 login wall — Sprint 9+",
		)
	case "ES":
		f.log.Info("familia_g: G.ES.1 FACONAUTO deferred",
			"country", country,
			"reason", "no public dealer member directory found — Sprint 9+",
		)
	case "BE":
		f.log.Info("familia_g: G.BE.1 TRAXIO deferred",
			"country", country,
			"reason", "no accessible member directory on public site — Sprint 9+",
		)
	case "CH":
		f.log.Info("familia_g: G.CH.1 AGVS-UPSA deferred",
			"country", country,
			"reason", "robots.txt blocks Solr search params; TYPO3+Solr SPA — Sprint 9+",
		)
	default:
		return result, fmt.Errorf("familia_g: unsupported country %q", country)
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

// HealthCheck verifies that the BOVAG endpoint is reachable.
func (f *FamilyG) HealthCheck(ctx context.Context) error {
	if err := f.bovag.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_g health: BOVAG: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
