// Package familia_f implements Family F — Aggregator dealer directories.
//
// Sprint 8 activates F.2 AutoScout24 using the Playwright browser module
// delivered in Sprint 7.
//
// Active sub-techniques:
//
//   - F.1 — mobile.de Händlersuche (DE)
//   - F.2 — AutoScout24 dealer-search (pan-EU: DE/FR/NL/BE/CH)
//   - F.4 — La Centrale Pro directory (FR)
//
// Deferred:
//   - F.3 — Autocasion dealer directory (ES)
//     Reason: Cloudflare challenge blocks all cloud-IP access.
//   - F.2 for ES: robots.txt connection error; path status unknown.
//
// Country → sub-technique mapping:
//
//	DE → F.1 (mobile.de) + F.2 (AutoScout24)
//	FR → F.4 (La Centrale) + F.2 (AutoScout24)
//	NL, BE, CH → F.2 (AutoScout24) only
//	ES → no source; logged and skipped
package familia_f

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_f/autoscout24"
	"cardex.eu/discovery/internal/families/familia_f/lacentrale"
	"cardex.eu/discovery/internal/families/familia_f/mobilede"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "F"
	familyName = "Aggregator dealer directories (mobile.de + AutoScout24 + La Centrale Pro)"
)

// FamilyF orchestrates the implemented F sub-techniques per country.
type FamilyF struct {
	mobilede    *mobilede.MobileDe
	lacentrale  *lacentrale.LaCentrale
	autoscout24 *autoscout24.AutoScout24
	log         *slog.Logger
}

// New constructs a FamilyF with production endpoints.
func New(graph kg.KnowledgeGraph, _ *sql.DB, b browser.Browser) *FamilyF {
	return &FamilyF{
		mobilede:    mobilede.New(graph),
		lacentrale:  lacentrale.New(graph),
		autoscout24: autoscout24.New(graph, b),
		log:         slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyF) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyF) Name() string { return familyName }

// Run executes the configured F sub-techniques for the given country.
func (f *FamilyF) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_f: sub-technique error", "sub", label, "err", err)
		}
	}

	switch country {
	case "DE":
		res1, err1 := f.mobilede.Run(ctx)
		collect(res1, err1, "mobile.de")
		res2, err2 := f.autoscout24.Run(ctx, country)
		collect(res2, err2, "autoscout24")

	case "FR":
		res1, err1 := f.lacentrale.Run(ctx)
		collect(res1, err1, "lacentrale")
		res2, err2 := f.autoscout24.Run(ctx, country)
		collect(res2, err2, "autoscout24")

	case "NL", "BE", "CH":
		res, err := f.autoscout24.Run(ctx, country)
		collect(res, err, "autoscout24")

	case "ES":
		// F.2 ES deferred: robots.txt inaccessible. F.3 Autocasion blocked by Cloudflare.
		f.log.Info("familia_f: no source configured for ES",
			"country", country,
			"deferred", "F.2 AutoScout24 ES (robots.txt error), F.3 Autocasion (Cloudflare)",
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
