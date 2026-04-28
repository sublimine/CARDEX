// Package shodan implements sub-technique N.2 -- Shodan free tier host intelligence.
//
// # Strategy
//
// For each dealer web presence from ListWebPresencesForInfraScan, N.2 queries
// the Shodan search API with query ssl:"{domain}" to find host IPs serving TLS
// certificates containing the dealer domain. Discovered IPs are stored as
// SHODAN_HOST_ID identifiers on the dealer.
//
// # Rate limits
//
// Free tier: 100 queries/month (~3/day). Configured inter-query sleep: 10 s.
// Authentication: SHODAN_API_KEY query parameter.
// If the key is absent, Run returns an empty result without error.
//
// # Shodan REST Search API
//
//	GET https://api.shodan.io/shodan/host/search?key={apikey}&query=ssl:{domain}
//
// Response (200 OK):
//
//	{
//	  "matches": [
//	    {"ip_str":"1.2.3.4","hostnames":["example.com"],"port":443}
//	  ],
//	  "total": 1
//	}
//
// Error response (401/429):
//
//	{"error": "Invalid API key."}
package shodan

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
	subTechID    = "N.2"
	subTechName  = "Shodan free tier SSL/host search (100 queries/month)"
	defaultBase  = "https://api.shodan.io"
	batchLimit   = 30              // web presences processed per Run call
	interQueryMs = 10_000         // 10 s gap to stay within 100 req/month free tier
)

// Shodan is the N.2 sub-technique client.
type Shodan struct {
	graph   kg.KnowledgeGraph
	apiKey  string
	baseURL string
	client  *http.Client
	log     *slog.Logger
}

// New constructs a Shodan client with production configuration.
// apiKey corresponds to the SHODAN_API_KEY env var.
func New(graph kg.KnowledgeGraph, apiKey string) *Shodan {
	return &Shodan{
		graph:   graph,
		apiKey:  apiKey,
		baseURL: defaultBase,
		client:  &http.Client{Timeout: 30 * time.Second},
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a Shodan client with a custom HTTP client and base URL.
// Used in tests to redirect requests to a mock server.
func NewWithClient(graph kg.KnowledgeGraph, apiKey, baseURL string, c *http.Client) *Shodan {
	return &Shodan{
		graph:   graph,
		apiKey:  apiKey,
		baseURL: baseURL,
		client:  c,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (s *Shodan) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (s *Shodan) Name() string { return subTechName }

type shodanResp struct {
	Matches []struct {
		IPStr     string   `json:"ip_str"`
		Hostnames []string `json:"hostnames"`
		Port      int      `json:"port"`
	} `json:"matches"`
	Total int    `json:"total"`
	Error string `json:"error,omitempty"`
}

// Run fetches dealer web presences for country, queries Shodan for host IPs
// whose TLS certificate matches each dealer domain, and stores new IPs as
// SHODAN_HOST_ID identifiers on the corresponding dealer.
func (s *Shodan) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	if s.apiKey == "" {
		s.log.Info("N.2 Shodan: skipped -- credentials not set",
			"hint", "set SHODAN_API_KEY to enable")
		return result, nil
	}

	start := time.Now()
	presences, err := s.graph.ListWebPresencesForInfraScan(ctx, country, batchLimit)
	if err != nil {
		return result, fmt.Errorf("N.2: list web presences: %w", err)
	}
	s.log.Info("N.2 Shodan: starting", "country", country, "domains", len(presences))

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
		found, searchErr := s.searchDomain(ctx, wp.Domain, wp.DealerID)
		if searchErr != nil {
			s.log.Warn("N.2 Shodan: domain query failed", "domain", wp.Domain, "err", searchErr)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

	result.Duration = time.Since(start)
	return result, nil
}

func (s *Shodan) searchDomain(ctx context.Context, domain, dealerID string) (int, error) {
	params := url.Values{
		"key":   {s.apiKey},
		"query": {fmt.Sprintf(`ssl:"%s"`, domain)},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		s.baseURL+"/shodan/host/search?"+params.Encode(), nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := s.client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return 0, fmt.Errorf("N.2: 429 rate limit -- monthly quota exceeded for domain %s", domain)
	}
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("N.2: HTTP %d for domain %s", resp.StatusCode, domain)
	}

	var data shodanResp
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return 0, fmt.Errorf("N.2: decode response: %w", err)
	}
	if data.Error != "" {
		return 0, fmt.Errorf("N.2: Shodan API error: %s", data.Error)
	}

	discovered := 0
	for _, match := range data.Matches {
		if match.IPStr == "" || dealerID == "" {
			continue
		}
		// Skip if this IP is already attached to any dealer.
		existing, _ := s.graph.FindDealerByIdentifier(ctx, kg.IdentifierShodanHostID, match.IPStr)
		if existing != "" {
			continue
		}
		if err := s.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierShodanHostID,
			IdentifierValue: match.IPStr,
			SourceFamily:    "N",
			ValidStatus:     "FOUND",
		}); err == nil {
			discovered++
			s.log.Debug("N.2 Shodan: new host IP stored", "ip", match.IPStr, "domain", domain, "dealer", dealerID)
		}
	}
	return discovered, nil
}
