// Package familia_d implements Family D — CMS + stack fingerprinting.
//
// Family D does NOT discover new dealers. It classifies already-indexed dealers
// by their website's CMS and hosting stack, enabling intelligent routing in the
// extraction pipeline (E01-E12).
//
// # Sub-techniques
//
//   - D.1 HTML meta + header fingerprinting (fingerprint package)
//   - D.2 CMS plugin detection — WordPress REST endpoints + Joomla components (plugins package)
//   - D.3 DMS hosted infrastructure detection (dms package)
//
// # Execution flow
//
// For each dealer_web_presence in the target country whose cms_scanned_at is
// absent or stale:
//
//  1. D.1: Fetch homepage and detect CMS/version.
//  2. D.2: If WordPress or Joomla, probe plugin endpoints.
//  3. D.3: Check redirect chain and HTML for DMS provider markers.
//  4. Persist cms_fingerprint_json + extraction_hints_json via KG.
//
// D.1 runs unconditionally; D.2 only when CMS is WordPress or Joomla;
// D.3 runs unconditionally (a custom site may still be DMS-hosted).
//
// # Rate limiting
//
// Between domains: 2-second sleep (polite crawl; dealer sites are SME-grade).
// Between plugin probes (D.2): no additional delay (same domain, HEAD requests).
//
// # BaseWeights["D"] = 0.0
//
// D is purely capacity/routing metadata. It does not bump dealer confidence.
package familia_d

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_d/dms"
	"cardex.eu/discovery/internal/families/familia_d/fingerprint"
	"cardex.eu/discovery/internal/families/familia_d/plugins"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "D"
	familyName = "CMS + stack fingerprinting"

	staleDays    = 30  // re-scan after 30 days
	batchSize    = 200 // domains per Run call
	domainSleep  = 2 * time.Second
)

// FamilyD orchestrates D.1/D.2/D.3 across all web presences for a country.
type FamilyD struct {
	graph        kg.KnowledgeGraph
	fingerprinter *fingerprint.Fingerprinter
	pluginDet    *plugins.Detector
	dmsDet       *dms.Detector
	log          *slog.Logger
}

// New constructs a FamilyD with production sub-technique instances.
func New(graph kg.KnowledgeGraph) *FamilyD {
	return &FamilyD{
		graph:        graph,
		fingerprinter: fingerprint.New(),
		pluginDet:    plugins.New(),
		dmsDet:       dms.New(),
		log:          slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyD) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyD) Name() string { return familyName }

// Run executes D.1/D.2/D.3 for all stale web presences in country.
func (f *FamilyD) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	presences, err := f.graph.ListWebPresencesForCMSScan(ctx, country, staleDays, batchSize)
	if err != nil {
		result.TotalErrors++
		result.FinishedAt = time.Now()
		result.Duration = time.Since(start)
		return result, fmt.Errorf("familia_d.Run: list presences: %w", err)
	}

	f.log.Info("familia_d: scan batch started",
		"country", country, "presences", len(presences))

	subResult := &runner.SubTechniqueResult{SubTechniqueID: "D.1-3", Country: country}

	for _, wp := range presences {
		if ctx.Err() != nil {
			break
		}

		if err := f.processPresence(ctx, wp, subResult); err != nil {
			f.log.Warn("familia_d: domain scan error",
				"domain", wp.Domain, "err", err)
			subResult.Errors++
		}

		// Polite inter-domain delay.
		select {
		case <-ctx.Done():
			goto done
		case <-time.After(domainSleep):
		}
	}

done:
	subResult.Duration = time.Since(start)
	result.SubResults = append(result.SubResults, subResult)
	result.TotalNew += subResult.Discovered
	result.TotalErrors += subResult.Errors
	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)

	if result.TotalErrors > 0 {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
	} else {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	}
	return result, nil
}

// processPresence runs D.1 → D.2 → D.3 for a single web presence and persists
// the results to the KG.
func (f *FamilyD) processPresence(
	ctx context.Context,
	wp *kg.DealerWebPresence,
	sub *runner.SubTechniqueResult,
) error {
	domain := wp.Domain

	// D.1: HTML/header fingerprinting
	cmsResult, err := f.fingerprinter.FingerprintDomain(ctx, domain)
	if err != nil {
		return fmt.Errorf("D.1 %q: %w", domain, err)
	}

	// D.2: Plugin detection (WordPress and Joomla only)
	var pluginResult *plugins.PluginResult
	if cmsResult.CMS == fingerprint.CMSWordPress || cmsResult.CMS == fingerprint.CMSJoomla {
		pluginResult, err = f.pluginDet.DetectPlugins(ctx, domain, string(cmsResult.CMS))
		if err != nil {
			f.log.Warn("D.2 error", "domain", domain, "err", err)
			pluginResult = &plugins.PluginResult{}
		}
		// Merge detected plugins into CMS result signals.
		cmsResult.Signals = append(cmsResult.Signals, pluginResult.Plugins...)
	}

	// D.3: DMS detection
	dmsResult, err := f.dmsDet.DetectDMS(ctx, domain)
	if err != nil {
		f.log.Warn("D.3 error", "domain", domain, "err", err)
	} else if dmsResult.Detected {
		cmsResult.Signals = append(cmsResult.Signals,
			"dms:"+string(dmsResult.Provider))
	}

	// Serialise CMS fingerprint JSON.
	cmsFPJSON, err := json.Marshal(cmsResult)
	if err != nil {
		return fmt.Errorf("marshal cms fingerprint: %w", err)
	}

	// Serialise extraction hints JSON.
	type hintsPayload struct {
		Endpoints []plugins.ExtractionEndpoint `json:"endpoints,omitempty"`
		DMS       string                        `json:"dms_provider,omitempty"`
		Notes     string                        `json:"notes,omitempty"`
	}
	hints := hintsPayload{}
	if pluginResult != nil {
		hints.Endpoints = pluginResult.Endpoints
	}
	if dmsResult != nil && dmsResult.Detected {
		hints.DMS = string(dmsResult.Provider)
	}
	if cmsResult.CMS == fingerprint.CMSCustom || cmsResult.CMS == fingerprint.CMSUnknown {
		hints.Notes = "no standard extraction endpoints detected; E-series strategy: DOM scrape or screenshot"
	}
	hintsJSON, err := json.Marshal(hints)
	if err != nil {
		return fmt.Errorf("marshal hints: %w", err)
	}

	if err := f.graph.UpsertWebTechnology(ctx, domain, string(cmsFPJSON), string(hintsJSON)); err != nil {
		return fmt.Errorf("upsert web technology: %w", err)
	}

	sub.Discovered++ // "discovered" here means "classified" — a web tech record was written
	f.log.Debug("familia_d: domain classified",
		"domain", domain,
		"cms", cmsResult.CMS,
		"confidence", cmsResult.Confidence,
		"dms_detected", dmsResult != nil && dmsResult.Detected,
	)
	return nil
}
