// Package ip_cluster implements sub-technique E.3 -- DMS IP clustering.
//
// # Strategy
//
// N.1 (Censys) and N.2 (Shodan) record CENSYS_HOST_ID and SHODAN_HOST_ID
// identifiers on dealer_identifier rows. When multiple dealers share the same
// host IP, it is a strong signal that they use a common hosting provider -- often
// the DMS vendor itself (e.g. CDK Global hosting all its German dealer sites on
// a shared farm, Modix hosting NL/BE dealers on a dedicated range).
//
// E.3 reads host IP clusters (≥3 co-hosted dealers) from the KG, then for each
// cluster that contains a country-matching dealer with a known DMS provider,
// propagates that provider to all other country-matching cluster members lacking one.
//
// # Why ≥3
//
// Two dealers sharing an IP is common for any generic shared hosting provider
// and does not imply a DMS relationship. Three or more co-hosted dealers with at
// least one known DMS provider is a much stronger signal.
//
// # Rate limits
//
// E.3 makes no external HTTP requests. All data comes from the KG (local SQLite).
// No sleep required.
package ip_cluster

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID  = "E.3"
	subTechName = "DMS IP clustering (co-hosted dealer DMS propagation)"
	minCluster  = 3     // minimum co-hosted dealers to attempt DMS propagation
	presenceCap = 10000 // max presences loaded per country
)

// presenceInfo caches per-domain DMS state for cluster propagation.
type presenceInfo struct {
	domain      string
	dmsProvider string // empty = not set
}

// IPClusterer is the E.3 sub-technique.
type IPClusterer struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs an IPClusterer with production configuration.
func New(graph kg.KnowledgeGraph) *IPClusterer {
	return &IPClusterer{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (e *IPClusterer) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (e *IPClusterer) Name() string { return subTechName }

// Run identifies co-hosted dealer clusters for the given country and propagates
// known DMS providers to cluster members that lack one.
func (e *IPClusterer) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	start := time.Now()

	// Load the country's web presences to build a dealer_id → presences map.
	wps, err := e.graph.ListWebPresencesForInfraScan(ctx, country, presenceCap)
	if err != nil {
		return result, fmt.Errorf("E.3: list web presences: %w", err)
	}

	// dealer_id → list of (domain, dmsProvider) for this country.
	byDealer := make(map[string][]presenceInfo, len(wps))
	for _, wp := range wps {
		prov := ""
		if wp.DMSProvider != nil {
			prov = *wp.DMSProvider
		}
		byDealer[wp.DealerID] = append(byDealer[wp.DealerID], presenceInfo{
			domain:      wp.Domain,
			dmsProvider: prov,
		})
	}

	// Retrieve global IP clusters (country-agnostic: Censys/Shodan see all dealers).
	clusters, err := e.graph.ListHostIPClusters(ctx, minCluster)
	if err != nil {
		return result, fmt.Errorf("E.3: ListHostIPClusters: %w", err)
	}
	e.log.Info("E.3 IP clustering: loaded clusters", "total_clusters", len(clusters), "country", country)

	for _, cluster := range clusters {
		if ctx.Err() != nil {
			break
		}
		found, err := e.propagateCluster(ctx, cluster, byDealer)
		if err != nil {
			e.log.Warn("E.3: cluster propagation error", "host_ip", cluster.HostIP, "err", err)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

	result.Duration = time.Since(start)
	return result, nil
}

// propagateCluster propagates the DMS provider from any cluster member to all
// other members in the byDealer map (i.e. those belonging to the current country).
// Returns the count of newly set providers.
func (e *IPClusterer) propagateCluster(
	ctx context.Context,
	cluster *kg.HostIPCluster,
	byDealer map[string][]presenceInfo,
) (int, error) {
	// Collect the country-scoped presences for all cluster members.
	type memberPresence struct {
		presenceInfo
		dealerID string
	}
	var members []memberPresence
	knownProvider := ""

	for _, dealerID := range cluster.DealerIDs {
		pis, ok := byDealer[dealerID]
		if !ok {
			continue // dealer not in this country
		}
		for _, pi := range pis {
			members = append(members, memberPresence{presenceInfo: pi, dealerID: dealerID})
			if pi.dmsProvider != "" && knownProvider == "" {
				knownProvider = pi.dmsProvider
			}
		}
	}

	if knownProvider == "" || len(members) < 2 {
		// Nothing to propagate: no known provider, or only one country member.
		return 0, nil
	}

	propagated := 0
	for _, m := range members {
		if m.dmsProvider != "" {
			continue // already has a provider
		}
		if err := e.graph.SetDMSProvider(ctx, m.domain, knownProvider); err != nil {
			e.log.Warn("E.3: SetDMSProvider failed",
				"domain", m.domain, "provider", knownProvider, "err", err)
			continue
		}
		e.log.Debug("E.3: DMS propagated via IP cluster",
			"host_ip", cluster.HostIP, "domain", m.domain, "provider", knownProvider)
		propagated++
	}
	return propagated, nil
}
