// Package familia_f implements Family F — Aggregator dealer directories.
//
// Sprint 5 delivers two sub-techniques out of four planned:
//
//   - F.1 — mobile.de Händlersuche (DE)  ← implemented
//   - F.4 — La Centrale Pro directory (FR) ← implemented
//
// Deferred to Sprint 6 (dedicated Playwright/browser sprint):
//   - F.2 — AutoScout24 dealer-search (pan-EU: DE/FR/ES/BE/NL/CH)
//     Reason: main dealer listing (/haendler/) is a client-side SPA with no
//     static JSON payload; country-specific paths (/garages/, /autobedrijven/)
//     are also blocked in AutoScout24's robots.txt.
//   - F.3 — Autocasion dealer directory (ES)
//     Reason: site is behind a Cloudflare challenge that blocks all cloud-IP
//     access; robots.txt could not be fetched to verify crawl permissions.
//
// Country → sub-technique mapping:
//
//	DE → F.1 (mobile.de)
//	FR → F.4 (La Centrale)
//	ES, BE, NL, CH → no Sprint 5 source; logged and skipped
package familia_f

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_f/lacentrale"
	"cardex.eu/discovery/internal/families/familia_f/mobilede"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "F"
	familyName = "Aggregator dealer directories (mobile.de + La Centrale Pro)"
)

// FamilyF orchestrates the implemented F sub-techniques per country.
type FamilyF struct {
	mobilede   *mobilede.MobileDe
	lacentrale *lacentrale.LaCentrale
	log        *slog.Logger
}

// New constructs a FamilyF with production endpoints.
func New(graph kg.KnowledgeGraph, _ *sql.DB) *FamilyF {
	return &FamilyF{
		mobilede:   mobilede.New(graph),
		lacentrale: lacentrale.New(graph),
		log:        slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyF) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyF) Name() string { return familyName }

// Run executes the configured F sub-techniques for the given country.
// Countries without a Sprint 5 source (ES, BE, NL, CH) return an empty result.
func (f *FamilyF) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	switch country {
	case "DE":
		res, err := f.mobilede.Run(ctx)
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_f: mobile.de error", "err", err)
		}

	case "FR":
		res, err := f.lacentrale.Run(ctx)
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_f: La Centrale error", "err", err)
		}

	case "ES", "BE", "NL", "CH":
		// F.2 (AutoScout24) and F.3 (Autocasion) deferred to Sprint 6.
		f.log.Info("familia_f: no Sprint-5 source configured",
			"country", country,
			"deferred", "F.2 AutoScout24 (SPA), F.3 Autocasion (Cloudflare)",
		)

	default:
		return result, fmt.Errorf("familia_f: unsupported country %q", country)
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

// HealthCheck verifies that the configured external endpoints are reachable.
func (f *FamilyF) HealthCheck(ctx context.Context) error {
	if err := f.mobilede.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_f health: mobile.de: %w", err)
	}
	if err := f.lacentrale.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_f health: La Centrale: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
