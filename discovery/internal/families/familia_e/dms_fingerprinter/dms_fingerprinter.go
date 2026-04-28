// Package dms_fingerprinter implements sub-technique E.1 -- extended EU
// automotive DMS provider fingerprinting.
//
// # Relationship to Family D (D.3)
//
// Family D sub-technique D.3 already detects DMS hosting for a subset of
// providers (dealersites.com, dealerinspire.com, dealerconnect.de,
// motormarket.de, flota.net, carssales.com). E.1 extends this with the full
// EU automotive DMS landscape:
//
//   - CDK Global (cdkglobal.com, cdksite.com)
//   - Reynolds & Reynolds Europe (reyrey.eu, reyrey.com)
//   - incadea by Cox Automotive (incadea.com)
//   - Carmen (carmen.de, carmen-autosoftware.de)
//   - AutoLine (autoline.de, autoline.eu)
//   - DealerSocket / Solera (dealersocket.com, soleraautomotive.com)
//   - Modix (modix.com, modix.de)
//   - iCar Software (icar-software.de)
//   - Brain Solutions (brain-solutions.fr)
//
// # Strategy
//
// For each dealer web presence:
//  1. If extraction_hints_json from D.3 already contains a DMS provider,
//     promote it directly to the dms_provider column without re-fetching.
//  2. Otherwise, run the extended fingerprint scan (HTTP redirect chain +
//     HTML body patterns) and write the result.
//
// # Rate limits
//
// 2 s between domain scans (same as D.3). Batch size: 200 per run.
package dms_fingerprinter

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID    = "E.1"
	subTechName  = "Extended EU automotive DMS provider fingerprinting"
	batchLimit   = 200
	domainSleep  = 2 * time.Second
	maxBodyBytes = 256 * 1024
	maxRedirects = 10
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// extendedProviders is the full EU automotive DMS provider list for E.1.
// Ordered by market presence (most common first for early-exit efficiency).
var extendedProviders = []string{
	// From D.3 (already deployed)
	"dealerconnect.de",
	"motormarket.de",
	"flota.net",
	"dealersites.com",
	"dealerinspire.com",
	"carssales.com",
	// New in E.1 -- EU market providers
	"cdkglobal.com",
	"cdksite.com",
	"incadea.com",
	"incadea.net",
	"modix.com",
	"modix.de",
	"reyrey.eu",
	"reyrey.com",
	"carmen.de",
	"carmen-autosoftware.de",
	"autoline.de",
	"autoline.eu",
	"dealersocket.com",
	"soleraautomotive.com",
	"icar-software.de",
	"brain-solutions.fr",
}

// DMSFingerprinter is the E.1 sub-technique.
type DMSFingerprinter struct {
	graph  kg.KnowledgeGraph
	client *http.Client
	log    *slog.Logger
}

// New constructs a DMSFingerprinter with production configuration.
func New(graph kg.KnowledgeGraph) *DMSFingerprinter {
	return &DMSFingerprinter{
		graph: graph,
		client: &http.Client{
			Timeout:       15 * time.Second,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		log: slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a DMSFingerprinter with a custom HTTP client.
// Used in tests.
func NewWithClient(graph kg.KnowledgeGraph, c *http.Client) *DMSFingerprinter {
	return &DMSFingerprinter{
		graph:  graph,
		client: c,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (e *DMSFingerprinter) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (e *DMSFingerprinter) Name() string { return subTechName }

// Run processes web presences for country: promotes D.3 results to dms_provider
// column, and runs extended fingerprinting on presences without a D.3 result.
func (e *DMSFingerprinter) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	start := time.Now()

	presences, err := e.graph.ListWebPresencesForInfraScan(ctx, country, batchLimit)
	if err != nil {
		return result, fmt.Errorf("E.1: list web presences: %w", err)
	}
	e.log.Info("E.1 DMS fingerprinter: starting", "country", country, "presences", len(presences))

	for i, wp := range presences {
		if ctx.Err() != nil {
			break
		}
		// Skip domains that already have a dms_provider value.
		if wp.DMSProvider != nil && *wp.DMSProvider != "" {
			result.Confirmed++
			continue
		}

		// Try to promote from D.3 extraction_hints_json first (zero extra requests).
		if provider := extractDMSFromHints(wp.ExtractionHintsJSON); provider != "" {
			if err := e.graph.SetDMSProvider(ctx, wp.Domain, provider); err != nil {
				e.log.Warn("E.1: SetDMSProvider failed", "domain", wp.Domain, "err", err)
			} else {
				result.Discovered++
				e.log.Debug("E.1: DMS promoted from D.3 hints", "domain", wp.Domain, "provider", provider)
			}
			continue
		}

		// Run extended fingerprint scan.
		if i > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(domainSleep):
			}
		}
		provider := e.fingerprintDomain(ctx, wp.Domain)
		if provider != "" {
			if err := e.graph.SetDMSProvider(ctx, wp.Domain, provider); err != nil {
				e.log.Warn("E.1: SetDMSProvider failed", "domain", wp.Domain, "err", err)
				result.Errors++
			} else {
				result.Discovered++
				e.log.Debug("E.1: DMS fingerprinted", "domain", wp.Domain, "provider", provider)
			}
		}
	}

done:
	result.Duration = time.Since(start)
	return result, nil
}

// extractDMSFromHints reads the dms_provider field from the extraction_hints_json
// blob written by D.3. Returns empty string when absent or unparseable.
func extractDMSFromHints(hintsJSON *string) string {
	if hintsJSON == nil || *hintsJSON == "" {
		return ""
	}
	var hints struct {
		DMS string `json:"dms_provider"`
	}
	if err := json.Unmarshal([]byte(*hintsJSON), &hints); err != nil {
		return ""
	}
	return hints.DMS
}

// fingerprintDomain returns the DMS provider for domain by inspecting the HTTP
// redirect chain and HTML body. Returns empty string when none detected.
func (e *DMSFingerprinter) fingerprintDomain(ctx context.Context, domain string) string {
	currentURL := "https://" + domain + "/"
	seen := map[string]bool{}

	for i := 0; i < maxRedirects; i++ {
		if seen[currentURL] {
			break
		}
		seen[currentURL] = true

		// Check URL itself before fetching.
		if p := matchProvider(currentURL); p != "" {
			return p
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, currentURL, nil)
		if err != nil {
			break
		}
		req.Header.Set("User-Agent", cardexUA)

		resp, err := e.client.Do(req)
		if err != nil {
			break
		}

		if isRedirect(resp.StatusCode) {
			loc := resp.Header.Get("Location")
			resp.Body.Close()
			if loc == "" {
				break
			}
			if strings.HasPrefix(loc, "/") {
				// Relative redirect -- resolve against current origin.
				if idx := strings.Index(currentURL[8:], "/"); idx >= 0 {
					loc = currentURL[:idx+8] + loc
				}
			}
			if p := matchProvider(loc); p != "" {
				return p
			}
			currentURL = loc
			continue
		}

		if resp.StatusCode == http.StatusOK {
			lr := io.LimitReader(resp.Body, maxBodyBytes)
			body, _ := io.ReadAll(lr)
			resp.Body.Close()
			bodyLower := strings.ToLower(string(body))
			for _, prov := range extendedProviders {
				if strings.Contains(bodyLower, prov) {
					return prov
				}
			}
		} else {
			resp.Body.Close()
		}
		break
	}
	return ""
}

// matchProvider returns the first provider that appears as a host suffix in rawURL.
func matchProvider(rawURL string) string {
	u := rawURL
	if idx := strings.Index(u, "://"); idx >= 0 {
		u = u[idx+3:]
	}
	if idx := strings.Index(u, "/"); idx >= 0 {
		u = u[:idx]
	}
	if idx := strings.LastIndex(u, ":"); idx >= 0 {
		u = u[:idx]
	}
	host := strings.ToLower(u)
	for _, p := range extendedProviders {
		if host == p || strings.HasSuffix(host, "."+p) {
			return p
		}
	}
	return ""
}

func isRedirect(code int) bool {
	switch code {
	case http.StatusMovedPermanently, http.StatusFound,
		http.StatusSeeOther, http.StatusTemporaryRedirect,
		http.StatusPermanentRedirect:
		return true
	}
	return false
}
