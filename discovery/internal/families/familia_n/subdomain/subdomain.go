// Package subdomain implements sub-technique N.3 -- automotive subdomain
// enumeration via DNS bruteforce.
//
// # Strategy
//
// For each dealer web presence domain, N.3 attempts DNS lookups for ~50
// automotive-specific subdomain prefixes (e.g. gebraucht.{domain},
// occasion.{domain}, leasing.{domain}). Any subdomain that resolves to at
// least one A/AAAA record is upserted into dealer_web_presence as a new
// candidate presence for the same dealer.
//
// This surfaces microsites and campaign domains not discovered by Certificate
// Transparency (Family C) or search engines (Family K): e.g.
// gebraucht.autohaus-mueller.de, leasing.citroen-paris.fr.
//
// # DNSDumpster
//
// DNSDumpster (dnsdumpster.com) provides passive DNS intelligence via a paid
// API (api.dnsdumpster.com). This sub-technique uses DNS bruteforce as the
// primary approach, which is free and produces equivalent coverage for the
// 50-keyword automotive wordlist. DNSDumpster integration is deferred to
// Sprint 18+ when the paid API budget is approved.
//
// # Rate limits
//
// No external API is called. DNS queries use the system resolver via
// net.DefaultResolver. Sleep: 100 ms between DNS lookups to avoid flooding
// the resolver. Batch size: 100 domains per Run call.
package subdomain

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID      = "N.3"
	subTechName    = "DNS subdomain enumeration (automotive wordlist bruteforce)"
	batchLimit     = 100          // domains per Run call
	interLookupMs  = 100          // 100 ms between DNS probes
)

// automotiveSubdomains is the bruteforce wordlist for N.3.
// ~50 automotive-relevant prefixes ordered by expected hit frequency.
var automotiveSubdomains = []string{
	"www", "shop", "cars", "autos", "vehicles", "fahrzeuge",
	"gebraucht", "gebrauchtwagen", "occasion", "occasions",
	"usado", "voitures", "usados", "ocasion",
	"stock", "inventory", "catalog", "catalogue",
	"angebote", "annonces", "offers",
	"portal", "dealer", "service", "parts",
	"ersatzteile", "pieces", "recambios",
	"werkstatt", "atelier", "taller", "officina",
	"booking", "termin", "appointment",
	"probefahrt", "testdrive", "essai",
	"angebot", "offer", "offre",
	"konfigurator", "configurator",
	"inzahlung", "reprise",
	"finanzierung", "financing", "financement",
	"leasing", "renting",
	"neuwagen", "new",
	"elektro", "electric",
	"nutzfahrzeuge", "commercial",
	"fleet", "news",
}

// lookupFunc is injectable for tests.
type lookupFunc func(ctx context.Context, host string) ([]string, error)

// SubdomainEnumerator is the N.3 sub-technique.
type SubdomainEnumerator struct {
	graph    kg.KnowledgeGraph
	lookup   lookupFunc
	log      *slog.Logger
}

// New constructs a SubdomainEnumerator using the system DNS resolver.
func New(graph kg.KnowledgeGraph) *SubdomainEnumerator {
	return &SubdomainEnumerator{
		graph:  graph,
		lookup: net.DefaultResolver.LookupHost,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithLookup constructs a SubdomainEnumerator with a custom DNS lookup function.
// Used in tests to avoid real DNS queries.
func NewWithLookup(graph kg.KnowledgeGraph, fn lookupFunc) *SubdomainEnumerator {
	return &SubdomainEnumerator{
		graph:  graph,
		lookup: fn,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (e *SubdomainEnumerator) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (e *SubdomainEnumerator) Name() string { return subTechName }

// Run enumerates automotive subdomains for each dealer domain in the given
// country. Resolved subdomains are upserted as new dealer_web_presence entries.
func (e *SubdomainEnumerator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}
	start := time.Now()

	presences, err := e.graph.ListWebPresencesForInfraScan(ctx, country, batchLimit)
	if err != nil {
		return result, fmt.Errorf("N.3: list web presences: %w", err)
	}
	e.log.Info("N.3 subdomain enum: starting", "country", country, "base_domains", len(presences))

	for _, wp := range presences {
		if ctx.Err() != nil {
			break
		}
		baseDomain := stripWWW(wp.Domain)
		found, enumErr := e.enumerateDomain(ctx, baseDomain, wp.DealerID)
		if enumErr != nil {
			e.log.Warn("N.3: enumeration error", "domain", baseDomain, "err", enumErr)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

	result.Duration = time.Since(start)
	return result, nil
}

func (e *SubdomainEnumerator) enumerateDomain(ctx context.Context, baseDomain, dealerID string) (int, error) {
	discovered := 0
	for i, prefix := range automotiveSubdomains {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			select {
			case <-ctx.Done():
				return discovered, nil
			case <-time.After(interLookupMs * time.Millisecond):
			}
		}

		candidate := prefix + "." + baseDomain

		// Check if we already have this subdomain.
		existing, _ := e.graph.FindDealerIDByDomain(ctx, candidate)
		if existing != "" {
			continue
		}

		addrs, lookupErr := e.lookup(ctx, candidate)
		if lookupErr != nil || len(addrs) == 0 {
			// NXDOMAIN or timeout -- not a live subdomain.
			continue
		}

		// Subdomain resolved -- upsert as a new web presence for the same dealer.
		webID := ulid.Make().String()
		if err := e.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
			WebID:                webID,
			DealerID:             dealerID,
			Domain:               candidate,
			URLRoot:              "https://" + candidate,
			DiscoveredByFamilies: "N",
		}); err != nil {
			e.log.Warn("N.3: upsert web presence failed", "subdomain", candidate, "err", err)
			continue
		}

		// Store the DNSDumpster-style identifier for the subdomain.
		if err := e.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierDNSDumpsterDomain,
			IdentifierValue: candidate,
			SourceFamily:    "N",
			ValidStatus:     "RESOLVED",
		}); err != nil {
			e.log.Warn("N.3: add identifier failed", "subdomain", candidate, "err", err)
		}

		discovered++
		e.log.Debug("N.3: subdomain found", "subdomain", candidate, "addrs", strings.Join(addrs, ","))
	}
	return discovered, nil
}

// stripWWW removes a leading "www." prefix so that we enumerate from the
// apex domain rather than probing "gebraucht.www.example.com".
func stripWWW(domain string) string {
	if strings.HasPrefix(domain, "www.") {
		return domain[4:]
	}
	return domain
}
