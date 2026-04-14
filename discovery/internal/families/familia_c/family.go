// Package familia_c implements Family C — Web Cartography.
//
// Sprint 4: three sub-techniques enrich existing dealer_web_presence rows
// and discover new subdomains:
//
//   - C.2 — Wayback Machine / Internet Archive  (historical coverage probe)
//   - C.3 — Certificate Transparency / crt.sh   (SAN enumeration)
//   - C.4 — Passive DNS / Hackertarget          (subdomain + IP resolution)
//
// Execution order per country:
//
//  1. Wayback Machine: probes 3 historical timestamps per domain, writes
//     wayback_coverage to metadata_json.  Conservative: 1 req/s.
//  2. Certificate Transparency: enumerates SANs for each domain, upserts new
//     subdomain web-presence rows.  Conservative: 1 req/3 s.
//  3. Passive DNS: resolves subdomains via Hackertarget (50 req/day budget).
//     Conservative: 1 req/2 s.
package familia_c

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_c/crtsh"
	"cardex.eu/discovery/internal/families/familia_c/passive_dns"
	"cardex.eu/discovery/internal/families/familia_c/wayback"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "C"
	familyName = "Web Cartography (Wayback + CT logs + Passive DNS)"
)

// FamilyC orchestrates sub-techniques C.2, C.3 and C.4 for web cartography.
type FamilyC struct {
	wayback  *wayback.Wayback
	crtsh    *crtsh.CrtSh
	pdns     *passive_dns.HackerTarget
	log      *slog.Logger
}

// New constructs a FamilyC with production endpoints.
func New(graph kg.KnowledgeGraph, database *sql.DB) *FamilyC {
	return &FamilyC{
		wayback: wayback.New(graph),
		crtsh:   crtsh.New(graph),
		pdns:    passive_dns.New(graph, database),
		log:     slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyC) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyC) Name() string { return familyName }

// Run executes all three C sub-techniques for the given country in order and
// returns an aggregated FamilyResult.
func (f *FamilyC) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	// ── C.2 — Wayback Machine ──────────────────────────────────────────────
	wbRes, err := f.wayback.RunAll(ctx, country)
	if wbRes != nil {
		result.SubResults = append(result.SubResults, wbRes)
		result.TotalNew += wbRes.Discovered
		result.TotalErrors += wbRes.Errors
	}
	if err != nil {
		result.TotalErrors++
		f.log.Warn("familia_c: Wayback error", "country", country, "err", err)
	}
	if ctx.Err() != nil {
		return finalize(result, start), nil
	}

	// ── C.3 — Certificate Transparency / crt.sh ───────────────────────────
	ctRes, err := f.crtsh.RunEnumerationForCountry(ctx, country)
	if ctRes != nil {
		result.SubResults = append(result.SubResults, ctRes)
		result.TotalNew += ctRes.Discovered
		result.TotalErrors += ctRes.Errors
	}
	if err != nil {
		result.TotalErrors++
		f.log.Warn("familia_c: crt.sh error", "country", country, "err", err)
	}
	if ctx.Err() != nil {
		return finalize(result, start), nil
	}

	// ── C.4 — Passive DNS / Hackertarget ──────────────────────────────────
	pdRes, err := f.pdns.RunAll(ctx, country)
	if pdRes != nil {
		result.SubResults = append(result.SubResults, pdRes)
		result.TotalNew += pdRes.Discovered
		result.TotalErrors += pdRes.Errors
	}
	if err != nil {
		result.TotalErrors++
		f.log.Warn("familia_c: Passive DNS error", "country", country, "err", err)
	}

	return finalize(result, start), nil
}

// HealthCheck verifies that all three external endpoints are reachable.
func (f *FamilyC) HealthCheck(ctx context.Context) error {
	if err := f.wayback.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_c health: Wayback: %w", err)
	}
	if err := f.crtsh.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_c health: crt.sh: %w", err)
	}
	if err := f.pdns.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_c health: Hackertarget: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}

func finalize(result *runner.FamilyResult, start time.Time) *runner.FamilyResult {
	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)
	if result.TotalErrors > 0 {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
	} else {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	}
	return result
}
