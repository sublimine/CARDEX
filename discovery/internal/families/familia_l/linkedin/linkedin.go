// Package linkedin implements sub-technique L.2 — LinkedIn Company profile
// cross-referencing.
//
// # STATUS: DEFERRED — R1 zero-legal-risk policy
//
// # Legal analysis
//
// LinkedIn's User Agreement, section 8.2 (as of 2024) explicitly prohibits:
//   "Use manual or automated software, devices, scripts, robots, backdoors or
//    other means or processes to access, 'scrape', 'crawl' or 'spider' any
//    web pages or other services contained in the Services."
//
// The landmark HiQ Labs, Inc. v. LinkedIn Corp. case (9th Cir. 2022, 31 F.4th
// 1180) established that scraping *publicly accessible* profile data does NOT
// violate the Computer Fraud and Abuse Act (CFAA). However:
//
//  1. The ruling applies to US federal law (CFAA) only; EU jurisdiction involves
//     different GDPR and database-right considerations under Directive 96/9/EC.
//  2. LinkedIn's ToS violation remains a civil-law risk: IP bans, cease-and-
//     desist letters, and injunctive relief under contract law.
//  3. GDPR Article 6(1)(f) (legitimate interest) may cover B2B profile data, but
//     a Data Protection Impact Assessment (DPIA) is required before processing.
//
// Under CARDEX policy R1 (zero legal risk during Phase 1–2 bootstrap), this
// sub-technique is not activated until all three conditions are met:
//
//  1. Legal review by EU-qualified counsel confirms compliance posture.
//  2. LinkedIn Partner API access obtained (Marketing Developer Platform, MDP).
//     Contact: developer.linkedin.com/partner-programs/marketing
//  3. DPIA completed and filed with the relevant EU supervisory authority.
//
// # What the implementation would do (design reference)
//
// For each dealer in the KG with a known web domain:
//  1. Derive LinkedIn company slug: lowercase canonical name, replace spaces with
//     hyphens, strip legal suffixes (GmbH, SA, SL, BV, etc.).
//  2. Attempt GET https://www.linkedin.com/company/{slug}
//     using browser.FetchHTML (LinkedIn is SPA-heavy).
//  3. Parse: company name, industry, HQ location, website, employee count.
//  4. Name + website cross-validate against KG canonical name + domain.
//  5. On match (confidence >= 0.80): upsert dealer_social_profile.
//  6. Rate limit: 1 req / 30 s (aggressive anti-bot; residential IP recommended).
//
// Estimated activation sprint: post-legal-clearance (tentative Sprint 22+).
package linkedin

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "L.2"
	subTechName = "LinkedIn Company cross-referencing (DEFERRED — R1 policy)"
)

// LinkedIn is the L.2 stub. Run always returns an empty result.
type LinkedIn struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a LinkedIn stub.
func New(graph kg.KnowledgeGraph) *LinkedIn {
	return &LinkedIn{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (l *LinkedIn) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (l *LinkedIn) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result. No requests are made.
func (l *LinkedIn) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	l.log.Info("L.2 LinkedIn Company: DEFERRED",
		"reason", "R1 zero-legal-risk policy: ToS 8.2 violation risk + EU GDPR DPIA required",
		"legal_ref", "HiQ v LinkedIn (9th Cir 2022) covers CFAA only; EU civil risk remains",
		"activation", "requires: (1) EU legal review, (2) MDP partner API, (3) DPIA filing",
		"country", country,
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}, nil
}
