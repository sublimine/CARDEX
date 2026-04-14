// Package familia_g implements Family G — Asociaciones sectoriales.
//
// Sprint 6 delivers one sub-technique out of six planned:
//
//   - G.NL.1 — BOVAG member directory (NL) ← implemented
//
// Deferred to Sprint dedicated with Playwright/authenticated scraping:
//
//   - G.DE.1 — ZDK Zentralverband Deutsches Kraftfahrzeuggewerbe
//     Reason: member directory at kfzgewerbe.de/mitglieder/ is behind a TYPO3
//     login wall (tx_felogin_login). No public member listing found.
//
//   - G.FR.1 — Mobilians (ex-CNPA umbrella)
//     Reason: mobilians.fr/annuaire/ is a JavaScript SPA. The underlying
//     search endpoint (libraries/search_es.php?type=json) returns HTTP 403
//     when accessed without the browser session context.
//
//   - G.ES.1 — FACONAUTO
//     Reason: no public dealer member directory found. /socios/, /directorio/,
//     /concesionarios/, /concesionarios-asociados/ all return 404. The
//     /socios/ page lists strategic partner companies (not individual dealers).
//
//   - G.BE.1 — TRAXIO (Belgium)
//     Reason: Umbraco CMS site; /fr/membres/ and /nl/leden/ return 404. No
//     accessible member directory URL found on the public site.
//
//   - G.CH.1 — AGVS-UPSA (Auto Gewerbe Verband Schweiz)
//     Reason: robots.txt explicitly blocks Solr search parameter paths
//     (Disallow: /*?tx_kesearch_* and /*?tx_solr[q]=*). The member directory
//     at /de/verband/mitglieder/mitgliederverzeichnis/ is a TYPO3+Solr SPA
//     with dynamic client-side rendering; crawling the search results would
//     violate the robots.txt directive.
//
// Country → sub-technique mapping (Sprint 6):
//
//	NL → G.NL.1 (BOVAG)
//	DE, FR, ES, BE, CH → no Sprint-6 source; logged and skipped
package familia_g

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_g/bovag"
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
	bovag *bovag.BOVAG
	log   *slog.Logger
}

// New constructs a FamilyG with production endpoints.
func New(graph kg.KnowledgeGraph) *FamilyG {
	return &FamilyG{
		bovag: bovag.New(graph),
		log:   slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyG) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyG) Name() string { return familyName }

// Run executes the configured G sub-techniques for the given country.
// Countries without a Sprint-6 source (DE, FR, ES, BE, CH) return an empty
// result with an informational log entry.
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

	case "DE":
		f.log.Info("familia_g: G.DE.1 ZDK deferred",
			"country", country,
			"reason", "member directory behind TYPO3 login wall — Sprint 7+",
		)
	case "FR":
		f.log.Info("familia_g: G.FR.1 Mobilians deferred",
			"country", country,
			"reason", "SPA + search API returns 403 without browser session — Sprint 7+",
		)
	case "ES":
		f.log.Info("familia_g: G.ES.1 FACONAUTO deferred",
			"country", country,
			"reason", "no public dealer member directory found — Sprint 7+",
		)
	case "BE":
		f.log.Info("familia_g: G.BE.1 TRAXIO deferred",
			"country", country,
			"reason", "no accessible member directory on public site — Sprint 7+",
		)
	case "CH":
		f.log.Info("familia_g: G.CH.1 AGVS-UPSA deferred",
			"country", country,
			"reason", "robots.txt blocks Solr search params; TYPO3+Solr SPA — Sprint 7+",
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
