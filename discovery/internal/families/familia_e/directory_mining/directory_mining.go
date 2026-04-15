// Package directory_mining implements sub-technique E.2 -- DMS customer
// directory mining.
//
// # STATUS: DEFERRED -- CDK Global and incadea customer portals require
// JavaScript rendering (Sprint 16+)
//
// # What E.2 would add
//
// CDK Global and incadea publish partial dealer directories accessible through
// their support and partner portals. These pages list current dealer customers
// by country, which would allow direct seeding of the KG with dealer names that
// are confirmed DMS users.
//
// # Why deferred
//
//  1. CDK Global's dealer search portal (dealerlookup.cdkglobal.com) renders its
//     results entirely via JavaScript (React SPA). Parsing the raw HTML response
//     yields no dealer data. Requires headless browser (Chromium/Playwright) to
//     execute the JS and extract rendered dealer list items.
//
//  2. incadea's partner directory (partners.incadea.com) is behind an OAuth2
//     login gate. Obtaining a machine-to-machine credential requires formal
//     partnership agreement with incadea / Cox Automotive. This is a business
//     relationship prerequisite, not a technical one.
//
//  3. Modix and Reynolds & Reynolds partner portals are similarly gated.
//
// # Activation path
//
//  1. Sprint 16: Integrate headless browser component (Playwright-Go or Rod)
//     into the discovery service for E.2 + Phase 3 extraction pipeline use.
//  2. Sprint 17: Implement CDK dealer lookup scraper using headless browser.
//  3. Sprint 18+: Negotiate incadea/Modix partner credentials.
//
// Estimated activation sprint: Sprint 17 (CDK), Sprint 18+ (incadea/Modix/Reynolds).
package directory_mining

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "E.2"
	subTechName = "DMS customer directory mining (DEFERRED -- JS rendering required)"
)

// DirectoryMiner is the E.2 stub.
type DirectoryMiner struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a DirectoryMiner stub.
func New(graph kg.KnowledgeGraph) *DirectoryMiner {
	return &DirectoryMiner{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (d *DirectoryMiner) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (d *DirectoryMiner) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result.
func (d *DirectoryMiner) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	d.log.Info("E.2 DMS directory mining: DEFERRED",
		"reason", "CDK Global dealer lookup requires JS rendering (React SPA); incadea partner portal requires OAuth2 partner credential",
		"activation", "Sprint 17 (CDK headless browser); Sprint 18+ (incadea/Modix/Reynolds credentials)",
		"country", country,
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}, nil
}
