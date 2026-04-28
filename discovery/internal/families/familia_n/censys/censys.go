// Package censys implements sub-technique N.1 -- Censys free tier host intelligence.
//
// # Strategy
//
// For each dealer web presence returned by ListWebPresencesForInfraScan, N.1
// queries the Censys v2 hosts/search API for hosts whose TLS certificate SANs
// include the dealer domain. This identifies IPv4/v6 addresses hosting dealer
// infrastructure.
//
// Discovered host IPs are stored as CENSYS_HOST_ID identifiers on the matching
// dealer entity. Cross-dealer IP clustering then reveals shared DMS providers.
//
// # Rate limits
//
// Free tier: 250 queries/month (~8/day). Configured inter-query sleep: 5 s.
// Authentication: HTTP Basic (CENSYS_API_ID : CENSYS_API_SECRET).
// If either credential is missing, Run returns an empty result without error.
//
// # Censys v2 Search API
//
//	POST https://search.censys.io/api/v2/hosts/search
//	Content-Type: application/json
//	Authorization: Basic <base64(api_id:api_secret)>
//
//	{"q":"services.tls.certificates.leaf_data.names: example.com","per_page":100}
//
// Response (200 OK):
//
//	{
//	  "code": 200,
//	  "result": {
//	    "total": 1,
//	    "hits": [{"ip":"1.2.3.4"}]
//	  }
//	}
//
// Response (429 Too Many Requests): free tier monthly quota exceeded.
package censys

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID    = "N.1"
	subTechName  = "Censys free tier TLS/host search (250 queries/month)"
	defaultBase  = "https://search.censys.io"
	batchLimit   = 50              // web presences processed per Run call
	interQueryMs = 5_000          // 5 s gap to stay within 250 req/month free tier
)

// Censys is the N.1 sub-technique client.
type Censys struct {
	graph   kg.KnowledgeGraph
	apiID   string
	apiSec  string
	baseURL string
	client  *http.Client
	log     *slog.Logger
}

// New constructs a Censys client with production configuration.
// apiID and apiSecret correspond to CENSYS_API_ID and CENSYS_API_SECRET.
func New(graph kg.KnowledgeGraph, apiID, apiSecret string) *Censys {
	return &Censys{
		graph:   graph,
		apiID:   apiID,
		apiSec:  apiSecret,
		baseURL: defaultBase,
		client:  &http.Client{Timeout: 30 * time.Second},
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a Censys client with a custom HTTP client and base URL.
// Used in tests to redirect requests to a mock server.
func NewWithClient(graph kg.KnowledgeGraph, apiID, apiSecret, baseURL string, c *http.Client) *Censys {
	return &Censys{
		graph:   graph,
		apiID:   apiID,
		apiSec:  apiSecret,
		baseURL: baseURL,
		client:  c,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *Censys) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *Censys) Name() string { return subTechName }

type searchReq struct {
	Q       string `json:"q"`
	PerPage int    `json:"per_page"`
}

type searchResp struct {
	Code   int    `json:"code"`
	Status string `json:"status"`
	Result struct {
		Total int `json:"total"`
		Hits  []struct {
			IP string `json:"ip"`
		} `json:"hits"`
	} `json:"result"`
}

// Run fetches dealer web presences for country, queries Censys for host IPs
// whose TLS SANs match each dealer domain, and stores new IPs as
// CENSYS_HOST_ID identifiers on the corresponding dealer.
func (c *Censys) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	if c.apiID == "" || c.apiSec == "" {
		c.log.Info("N.1 Censys: skipped -- credentials not set",
			"hint", "set CENSYS_API_ID and CENSYS_API_SECRET to enable")
		return result, nil
	}

	start := time.Now()
	presences, err := c.graph.ListWebPresencesForInfraScan(ctx, country, batchLimit)
	if err != nil {
		return result, fmt.Errorf("N.1: list web presences: %w", err)
	}
	c.log.Info("N.1 Censys: starting", "country", country, "domains", len(presences))

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
		found, searchErr := c.searchDomain(ctx, wp.Domain, wp.DealerID)
		if searchErr != nil {
			c.log.Warn("N.1 Censys: domain query failed", "domain", wp.Domain, "err", searchErr)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

	result.Duration = time.Since(start)
	return result, nil
}

func (c *Censys) searchDomain(ctx context.Context, domain, dealerID string) (int, error) {
	query := fmt.Sprintf("services.tls.certificates.leaf_data.names: %s", domain)
	body, _ := json.Marshal(searchReq{Q: query, PerPage: 100})

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/v2/hosts/search", bytes.NewReader(body))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.SetBasicAuth(c.apiID, c.apiSec)

	resp, err := c.client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return 0, fmt.Errorf("N.1: 429 rate limit -- monthly quota exceeded for domain %s", domain)
	}
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("N.1: HTTP %d for domain %s", resp.StatusCode, domain)
	}

	var data searchResp
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return 0, fmt.Errorf("N.1: decode response: %w", err)
	}

	discovered := 0
	for _, hit := range data.Result.Hits {
		if hit.IP == "" || dealerID == "" {
			continue
		}
		// Skip if this IP is already attached to any dealer.
		existing, _ := c.graph.FindDealerByIdentifier(ctx, kg.IdentifierCensysHostID, hit.IP)
		if existing != "" {
			continue
		}
		if err := c.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierCensysHostID,
			IdentifierValue: hit.IP,
			SourceFamily:    "N",
			ValidStatus:     "FOUND",
		}); err == nil {
			discovered++
			c.log.Debug("N.1 Censys: new host IP stored", "ip", hit.IP, "domain", domain, "dealer", dealerID)
		}
	}
	return discovered, nil
}
