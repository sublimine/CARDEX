// Package dms implements sub-technique D.3 — DMS hosted infrastructure
// detection.
//
// # What it does
//
// For each dealer domain, D.3 checks whether the dealer site is served by a
// known DMS (Dealer Management System) hosting platform. Detection uses two
// complementary methods:
//
//  1. Redirect chain inspection: follow up to 10 HTTP redirects. If any
//     redirect target domain matches a known DMS provider, the dealer is
//     classified as hosted on that platform.
//
//  2. HTML template fingerprint: scan the response body for known DMS-specific
//     JS includes, CSS classes, or meta tags that are not removable by the
//     dealer.
//
// # DMS providers covered
//
//   - DealerSite (US-origin, EU presence): dealersites.com, dealerinspire.com
//   - DealerConnect (DE): dealerconnect.de
//   - MotorMarket (DE): motormarket.de
//   - Flota.net (ES): flota.net
//   - CarsSales.com white-label: carssales.com
//
// # Relationship to Family E
//
// D.3 detects DMS hosting per individual dealer. Family E (deferred Sprint 13+)
// maps the provider-side infrastructure — the same provider from the opposite
// angle. D.3 results feed Family E by populating dealer_web_presence.dms_provider.
//
// BaseWeights["D"] = 0.0 -- classification only.
package dms

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

const (
	subTechID   = "D.3"
	subTechName = "DMS hosted infrastructure detection"

	defaultTimeout = 15 * time.Second
	maxBodyBytes   = 256 * 1024
	maxRedirects   = 10
	cardexUA       = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// DMSProvider identifies a known DMS hosting platform.
type DMSProvider string

const (
	ProviderDealerSite    DMSProvider = "dealersites.com"
	ProviderDealerInspire DMSProvider = "dealerinspire.com"
	ProviderDealerConnect DMSProvider = "dealerconnect.de"
	ProviderMotorMarket   DMSProvider = "motormarket.de"
	ProviderFlotaNet      DMSProvider = "flota.net"
	ProviderCarsSales     DMSProvider = "carssales.com"
)

// knownProviders is the ordered list of DMS domain suffixes to check in redirect
// chains and HTML bodies.
var knownProviders = []DMSProvider{
	ProviderDealerSite,
	ProviderDealerInspire,
	ProviderDealerConnect,
	ProviderMotorMarket,
	ProviderFlotaNet,
	ProviderCarsSales,
}

// DMSResult is the output of D.3 for a single domain.
type DMSResult struct {
	Detected   bool        `json:"detected"`
	Provider   DMSProvider `json:"provider,omitempty"` // empty when Detected=false
	Method     string      `json:"method,omitempty"`   // "redirect" or "html_template"
	Evidence   string      `json:"evidence,omitempty"` // redirect URL or matched pattern
	ScannedAt  string      `json:"scanned_at"`
}

// Detector checks whether a dealer domain is hosted on a known DMS platform.
type Detector struct {
	client *http.Client
	log    *slog.Logger
}

// New returns a Detector with production HTTP settings (redirects tracked manually).
func New() *Detector {
	return NewWithClient(nil)
}

// NewWithClient returns a Detector using the supplied HTTP client. Pass nil to
// use production defaults.
func NewWithClient(c *http.Client) *Detector {
	if c == nil {
		// We manage redirects ourselves to inspect the redirect chain.
		c = &http.Client{
			Timeout:       defaultTimeout,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		}
	}
	return &Detector{
		client: c,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (d *Detector) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (d *Detector) Name() string { return subTechName }

// DetectDMS checks domain for DMS hosting. Returns a DMSResult regardless of
// whether a DMS was found (Detected=false when none found).
func (d *Detector) DetectDMS(ctx context.Context, domain string) (*DMSResult, error) {
	scannedAt := time.Now().UTC().Format(time.RFC3339)

	// Follow redirect chain manually.
	currentURL := "https://" + domain + "/"
	seen := map[string]bool{}

	for i := 0; i < maxRedirects; i++ {
		if seen[currentURL] {
			break // redirect loop
		}
		seen[currentURL] = true

		// Check if any redirect target is a known DMS provider.
		for _, p := range knownProviders {
			if hostContainsProvider(currentURL, string(p)) {
				return &DMSResult{
					Detected:  true,
					Provider:  p,
					Method:    "redirect",
					Evidence:  currentURL,
					ScannedAt: scannedAt,
				}, nil
			}
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, currentURL, nil)
		if err != nil {
			break
		}
		req.Header.Set("User-Agent", cardexUA)

		resp, err := d.client.Do(req)
		if err != nil {
			break
		}

		if isRedirect(resp.StatusCode) {
			loc := resp.Header.Get("Location")
			resp.Body.Close()
			if loc == "" {
				break
			}
			// Resolve relative redirect
			if strings.HasPrefix(loc, "/") {
				loc = currentURL[:strings.Index(currentURL[8:], "/")+8] + loc
			}
			// Check the redirect target itself
			for _, p := range knownProviders {
				if hostContainsProvider(loc, string(p)) {
					return &DMSResult{
						Detected:  true,
						Provider:  p,
						Method:    "redirect",
						Evidence:  loc,
						ScannedAt: scannedAt,
					}, nil
				}
			}
			currentURL = loc
			continue
		}

		// Final response: scan HTML body for DMS fingerprints.
		if resp.StatusCode == http.StatusOK {
			lr := io.LimitReader(resp.Body, maxBodyBytes)
			body, _ := io.ReadAll(lr)
			resp.Body.Close()

			bodyStr := string(body)
			for _, p := range knownProviders {
				if strings.Contains(bodyStr, string(p)) {
					return &DMSResult{
						Detected:  true,
						Provider:  p,
						Method:    "html_template",
						Evidence:  fmt.Sprintf("body contains %q", p),
						ScannedAt: scannedAt,
					}, nil
				}
			}
		} else {
			resp.Body.Close()
		}
		break
	}

	return &DMSResult{Detected: false, ScannedAt: scannedAt}, nil
}

// hostContainsProvider returns true if rawURL's host ends with provider.
func hostContainsProvider(rawURL, provider string) bool {
	// Strip scheme
	u := rawURL
	if idx := strings.Index(u, "://"); idx >= 0 {
		u = u[idx+3:]
	}
	// Strip path
	if idx := strings.Index(u, "/"); idx >= 0 {
		u = u[:idx]
	}
	// Strip port
	if idx := strings.LastIndex(u, ":"); idx >= 0 {
		u = u[:idx]
	}
	host := strings.ToLower(u)
	p := strings.ToLower(provider)
	return host == p || strings.HasSuffix(host, "."+p)
}

func isRedirect(code int) bool {
	return code == http.StatusMovedPermanently ||
		code == http.StatusFound ||
		code == http.StatusSeeOther ||
		code == http.StatusTemporaryRedirect ||
		code == http.StatusPermanentRedirect
}
