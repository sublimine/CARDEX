// Package crtsh implements sub-technique C.3 — Certificate Transparency / crt.sh.
//
// Two operational modes:
//
//  1. Domain enumeration: for each domain already in dealer_web_presence, query
//     crt.sh for all certificates covering that domain and extract unique SAN
//     entries (subdomains).  New subdomains are stored as DealerWebPresence rows.
//
//  2. Keyword scan: issue wildcard queries such as "%.auto-example.de" to crt.sh
//     to discover new dealers whose domains match automotive patterns.  Matching
//     domains are upserted as new DealerEntity + DealerWebPresence rows.
//
// crt.sh API (verified 2026-04-14):
//
//	GET https://crt.sh/?q={query}&output=json
//
// Response: JSON array of certificate log entries.  The name_value field
// contains one or more newline-separated domain names (SANs).
//
// Rate limiting: 1 request per 3 seconds (conservative; crt.sh is a public
// service backed by Sectigo; no published limit, but heavy querying is blocked).
package crtsh

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultCrtShURL  = "https://crt.sh"
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "C"
	subTechID          = "C.3"
	subTechName        = "Certificate Transparency / crt.sh"
)

// certEntry is a single row from the crt.sh JSON response.
type certEntry struct {
	IssuerCAID     int    `json:"issuer_ca_id"`
	IssuerName     string `json:"issuer_name"`
	CommonName     string `json:"common_name"`
	NameValue      string `json:"name_value"`   // newline-separated SANs
	ID             int64  `json:"id"`
	EntryTimestamp string `json:"entry_timestamp"`
	NotBefore      string `json:"not_before"`
	NotAfter       string `json:"not_after"`
}

// CrtSh executes C.3 sub-technique queries.
type CrtSh struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New creates a CrtSh executor with the production crt.sh endpoint.
func New(graph kg.KnowledgeGraph) *CrtSh {
	return NewWithBaseURL(graph, defaultCrtShURL, defaultReqInterval)
}

// NewWithBaseURL creates a CrtSh executor with a custom endpoint and request
// interval (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *CrtSh {
	return &CrtSh{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *CrtSh) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *CrtSh) Name() string { return subTechName }

// ── Domain enumeration mode ──────────────────────────────────────────────────

// RunForDomain queries crt.sh for all certificates that cover the given domain
// and returns the deduplicated set of SAN entries (subdomains and alt names).
// Wildcard SANs (e.g. "*.example.de") are included as-is so callers can decide
// whether to strip the wildcard prefix.
func (c *CrtSh) RunForDomain(ctx context.Context, domain string) ([]string, error) {
	entries, err := c.fetch(ctx, domain)
	if err != nil {
		return nil, err
	}
	return extractSANs(entries, domain), nil
}

// RunEnumerationForCountry iterates over all dealer_web_presence rows for the
// given country, probes each domain on crt.sh, and upserts newly-discovered
// subdomain web presences back into the KG.
func (c *CrtSh) RunEnumerationForCountry(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	presences, err := c.graph.ListWebPresencesByCountry(ctx, country)
	if err != nil {
		return result, fmt.Errorf("crtsh.RunEnumeration %s: %w", country, err)
	}

	for i, wp := range presences {
		if ctx.Err() != nil {
			break
		}
		if i > 0 && c.reqInterval > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(c.reqInterval):
			}
		}

		sans, err := c.RunForDomain(ctx, wp.Domain)
		if err != nil {
			c.log.Warn("crtsh: enumeration error", "domain", wp.Domain, "err", err)
			result.Errors++
			continue
		}

		for _, san := range sans {
			// Skip the root domain itself — it's already in the KG.
			if san == wp.Domain || strings.HasPrefix(san, "*.") {
				continue
			}
			// Only record proper subdomains.
			if !strings.HasSuffix(san, "."+wp.Domain) {
				continue
			}
			upserted, err := c.upsertSubdomain(ctx, wp.DealerID, wp.Domain, san)
			if err != nil {
				c.log.Warn("crtsh: subdomain upsert error", "san", san, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Confirmed++
				metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
			}
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	return result, nil
}

// upsertSubdomain inserts a new DealerWebPresence row for a subdomain discovered
// via Certificate Transparency. Returns true when a new row was created.
func (c *CrtSh) upsertSubdomain(ctx context.Context, dealerID, rootDomain, subdomain string) (bool, error) {
	// Check whether this subdomain is already known.
	existing, err := c.graph.FindDealerIDByDomain(ctx, subdomain)
	if err != nil {
		return false, err
	}
	if existing != "" {
		return false, nil // already in KG
	}

	wp := &kg.DealerWebPresence{
		WebID:                ulid.Make().String(),
		DealerID:             dealerID,
		Domain:               subdomain,
		URLRoot:              "https://" + subdomain,
		DiscoveredByFamilies: familyID,
	}
	if err := c.graph.UpsertWebPresence(ctx, wp); err != nil {
		return false, err
	}
	return true, nil
}

// ── Keyword scan mode ────────────────────────────────────────────────────────

// KeywordScanResult holds the outcome of a single keyword scan query.
type KeywordScanResult struct {
	Query     string
	Domains   []string // unique domains extracted from matching certificates
}

// RunKeywordScan queries crt.sh for certificates whose domain names match the
// given wildcard pattern (e.g. "%.auto-dealer.de") and returns the unique
// domain names found.  The caller is responsible for filtering and upsert.
func (c *CrtSh) RunKeywordScan(ctx context.Context, pattern string) (*KeywordScanResult, error) {
	entries, err := c.fetch(ctx, pattern)
	if err != nil {
		return nil, err
	}

	seen := make(map[string]struct{})
	for _, entry := range entries {
		for _, san := range splitNameValue(entry.NameValue) {
			if san != "" {
				seen[san] = struct{}{}
			}
		}
		if entry.CommonName != "" {
			seen[entry.CommonName] = struct{}{}
		}
	}

	domains := make([]string, 0, len(seen))
	for d := range seen {
		domains = append(domains, d)
	}

	return &KeywordScanResult{Query: pattern, Domains: domains}, nil
}

// ── HTTP layer ───────────────────────────────────────────────────────────────

// fetch performs a single GET request to the crt.sh JSON API and decodes the
// certificate entries.
func (c *CrtSh) fetch(ctx context.Context, query string) ([]certEntry, error) {
	reqURL := c.baseURL + "/?q=" + url.QueryEscape(query) + "&output=json"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("crtsh: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("crtsh: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
		return nil, fmt.Errorf("crtsh: HTTP %d: %s", resp.StatusCode, string(raw))
	}

	var entries []certEntry
	if err := json.NewDecoder(resp.Body).Decode(&entries); err != nil {
		return nil, fmt.Errorf("crtsh: decode JSON: %w", err)
	}
	return entries, nil
}

// HealthCheck sends a minimal probe to verify crt.sh is reachable.
func (c *CrtSh) HealthCheck(ctx context.Context) error {
	reqURL := c.baseURL + "/?q=example.com&output=json"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("crtsh health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("crtsh health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// extractSANs returns all unique SAN entries from the given certificate entries
// that are related to rootDomain (exact match or subdomain of rootDomain).
func extractSANs(entries []certEntry, rootDomain string) []string {
	seen := make(map[string]struct{})
	suffix := "." + rootDomain

	for _, e := range entries {
		for _, san := range splitNameValue(e.NameValue) {
			if san == rootDomain ||
				strings.HasSuffix(san, suffix) ||
				san == "*."+rootDomain {
				seen[san] = struct{}{}
			}
		}
	}

	result := make([]string, 0, len(seen))
	for s := range seen {
		result = append(result, s)
	}
	return result
}

// splitNameValue splits a crt.sh name_value field (newline-separated SANs)
// into individual domain strings, trimming whitespace.
func splitNameValue(nameValue string) []string {
	raw := strings.Split(nameValue, "\n")
	out := make([]string, 0, len(raw))
	for _, s := range raw {
		if t := strings.TrimSpace(s); t != "" {
			out = append(out, t)
		}
	}
	return out
}
