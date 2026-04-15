// Package reverseip implements sub-technique N.4 -- reverse IP lookup via
// ViewDNS.info.
//
// # Strategy
//
// For each dealer domain in the KG, N.4 queries the ViewDNS.info Reverse IP
// API to discover all other domains co-hosted on the same IP address. Co-hosted
// domains are cross-referenced against dealer_web_presence:
//
//   - Known domain  -> no action (already in KG)
//   - Unknown domain -> UpsertWebPresence as a new candidate for the same dealer
//
// The primary signal is shared-DMS detection: multiple dealers on the same IP
// typically share a DMS provider's hosted infrastructure. The clustering output
// feeds back into Family D's DMSProvider field.
//
// # Rate limits
//
// ViewDNS.info free tier: 10 requests/hour per API key. Configured inter-query
// sleep: 360 s (6 min) to stay within the hourly budget. Batch size: 10 domains
// per Run call.
// Authentication: VIEWDNS_API_KEY query parameter.
// If absent, Run returns an empty result without error.
//
// # ViewDNS Reverse IP API
//
//	GET https://api.viewdns.info/reverseip/?host={domain}&apikey={key}&output=json
//
// Response (200 OK):
//
//	{
//	  "query": "example.com",
//	  "response": {
//	    "domain_count": "3",
//	    "domains": [
//	      {"name": "cohosted1.com"},
//	      {"name": "cohosted2.com"}
//	    ]
//	  }
//	}
package reverseip

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID    = "N.4"
	subTechName  = "ViewDNS.info reverse IP lookup (10 req/h)"
	defaultBase  = "https://api.viewdns.info"
	batchLimit   = 10              // domains per Run call (10 req/h free tier)
	interQueryMs = 360_000        // 6 min between queries to stay within 10/h limit
)

// ReverseIP is the N.4 sub-technique client.
type ReverseIP struct {
	graph   kg.KnowledgeGraph
	apiKey  string
	baseURL string
	client  *http.Client
	log     *slog.Logger
}

// New constructs a ReverseIP client with production configuration.
// apiKey corresponds to the VIEWDNS_API_KEY env var.
func New(graph kg.KnowledgeGraph, apiKey string) *ReverseIP {
	return &ReverseIP{
		graph:   graph,
		apiKey:  apiKey,
		baseURL: defaultBase,
		client:  &http.Client{Timeout: 30 * time.Second},
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a ReverseIP client with a custom HTTP client and base URL.
// Used in tests to redirect requests to a mock server.
func NewWithClient(graph kg.KnowledgeGraph, apiKey, baseURL string, c *http.Client) *ReverseIP {
	return &ReverseIP{
		graph:   graph,
		apiKey:  apiKey,
		baseURL: baseURL,
		client:  c,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (r *ReverseIP) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (r *ReverseIP) Name() string { return subTechName }

type viewDNSResp struct {
	Query    string `json:"query"`
	Response struct {
		DomainCount string `json:"domain_count"`
		Domains     []struct {
			Name string `json:"name"`
		} `json:"domains"`
	} `json:"response"`
}

// Run fetches a batch of dealer web presences for country, queries ViewDNS
// for co-hosted domains on the same IP, and upserts unknown domains as new
// web presence candidates for the source dealer.
func (r *ReverseIP) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	if r.apiKey == "" {
		r.log.Info("N.4 ReverseIP: skipped -- credentials not set",
			"hint", "set VIEWDNS_API_KEY to enable")
		return result, nil
	}

	start := time.Now()
	presences, err := r.graph.ListWebPresencesForInfraScan(ctx, country, batchLimit)
	if err != nil {
		return result, fmt.Errorf("N.4: list web presences: %w", err)
	}
	r.log.Info("N.4 ReverseIP: starting", "country", country, "domains", len(presences))

outer:
	for i, wp := range presences {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			select {
			case <-ctx.Done():
				break outer
			case <-time.After(interQueryMs * time.Millisecond):
			}
		}
		found, lookupErr := r.reverseLookup(ctx, wp.Domain, wp.DealerID)
		if lookupErr != nil {
			r.log.Warn("N.4 ReverseIP: lookup failed", "domain", wp.Domain, "err", lookupErr)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

	result.Duration = time.Since(start)
	return result, nil
}

func (r *ReverseIP) reverseLookup(ctx context.Context, domain, dealerID string) (int, error) {
	params := url.Values{
		"host":   {domain},
		"apikey": {r.apiKey},
		"output": {"json"},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		r.baseURL+"/reverseip/?"+params.Encode(), nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := r.client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return 0, fmt.Errorf("N.4: 429 rate limit -- hourly quota exceeded for domain %s", domain)
	}
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("N.4: HTTP %d for domain %s", resp.StatusCode, domain)
	}

	var data viewDNSResp
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return 0, fmt.Errorf("N.4: decode response: %w", err)
	}

	discovered := 0
	for _, d := range data.Response.Domains {
		if d.Name == "" || d.Name == domain {
			continue
		}
		// Skip if already in KG.
		existing, _ := r.graph.FindDealerIDByDomain(ctx, d.Name)
		if existing != "" {
			continue
		}
		// Upsert co-hosted domain as a new web presence candidate.
		if err := r.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
			WebID:                ulid.Make().String(),
			DealerID:             dealerID,
			Domain:               d.Name,
			URLRoot:              "https://" + d.Name,
			DiscoveredByFamilies: "N",
		}); err != nil {
			r.log.Warn("N.4: upsert co-hosted domain failed", "domain", d.Name, "err", err)
			continue
		}
		discovered++
		r.log.Debug("N.4 ReverseIP: co-hosted domain found", "cohosted", d.Name, "source", domain)
	}
	return discovered, nil
}
