// Package familia_n implements Family N -- infrastructure intelligence.
//
// Family N queries external host intelligence services and performs active DNS
// probing to enrich the KG with infrastructure-layer signals:
//
//   - N.1: Censys free tier TLS/host search (250 queries/month)
//   - N.2: Shodan free tier SSL/host search (100 queries/month)
//   - N.3: DNS subdomain enumeration (automotive wordlist, ~50 prefixes, no API)
//   - N.4: ViewDNS.info reverse IP lookup (10 req/h)
//
// All sub-techniques are country-agnostic (domain-based), but respect the
// country filter when listing web presences to scan.
//
// BaseWeights["N"] = 0.05 -- infrastructure signals complement Familia C+E;
// they do not independently confirm dealer status.
//
// Required environment variables (each sub-technique gracefully skips when absent):
//
//	CENSYS_API_ID      -- Censys account API ID   (N.1)
//	CENSYS_API_SECRET  -- Censys account secret   (N.1)
//	SHODAN_API_KEY     -- Shodan API key           (N.2)
//	VIEWDNS_API_KEY    -- ViewDNS.info API key     (N.4)
package familia_n

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_n/censys"
	"cardex.eu/discovery/internal/families/familia_n/reverseip"
	"cardex.eu/discovery/internal/families/familia_n/shodan"
	"cardex.eu/discovery/internal/families/familia_n/subdomain"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "N"
	familyName = "Infrastructure intelligence"
)

// FamilyN orchestrates all N infrastructure sub-techniques.
type FamilyN struct {
	censys    *censys.Censys
	shodan    *shodan.Shodan
	subdomain *subdomain.SubdomainEnumerator
	reverseIP *reverseip.ReverseIP
	log       *slog.Logger
}

// New constructs a FamilyN with production configuration.
// Missing API keys cause their respective sub-techniques to skip gracefully.
func New(
	graph kg.KnowledgeGraph,
	censysAPIID, censysAPISecret string,
	shodanAPIKey string,
	viewDNSAPIKey string,
) *FamilyN {
	return &FamilyN{
		censys:    censys.New(graph, censysAPIID, censysAPISecret),
		shodan:    shodan.New(graph, shodanAPIKey),
		subdomain: subdomain.New(graph),
		reverseIP: reverseip.New(graph, viewDNSAPIKey),
		log:       slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyN) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyN) Name() string { return familyName }

// Run executes all N sub-techniques for the given country.
func (f *FamilyN) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_n: sub-technique error",
				"sub", label, "country", country, "err", err)
		}
	}

	// N.1 Censys -- TLS cert host lookup
	res1, err1 := f.censys.Run(ctx, country)
	collect(res1, err1, "censys")

	// N.2 Shodan -- SSL host search
	if ctx.Err() == nil {
		res2, err2 := f.shodan.Run(ctx, country)
		collect(res2, err2, "shodan")
	}

	// N.3 DNS subdomain enumeration -- automotive wordlist
	if ctx.Err() == nil {
		res3, err3 := f.subdomain.Run(ctx, country)
		collect(res3, err3, "subdomain")
	}

	// N.4 ViewDNS reverse IP -- co-hosted domain discovery
	if ctx.Err() == nil {
		res4, err4 := f.reverseIP.Run(ctx, country)
		collect(res4, err4, "reverseip")
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

// HealthCheck satisfies the runner.FamilyRunner interface.
// Returns nil unless country is explicitly unsupported (N is country-agnostic).
func (f *FamilyN) HealthCheck(_ context.Context) error {
	return fmt.Errorf("familia_n: HealthCheck not implemented -- N sub-techniques are country-agnostic")
}
