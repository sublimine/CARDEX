// Package wayback_monitor implements sub-technique O.3 -- Wayback Machine
// reactive monitoring for dealer web presence archival.
//
// # STATUS: DEFERRED -- covered by C.2 and Sprint 16+ roadmap
//
// # What O.3 would add
//
// Familia C sub-technique C.2 already queries the Wayback Machine CDX API
// for historical domain snapshots. O.3 would extend this with:
//
//  1. Reactive monitoring: subscribe to Wayback Machine's SavePageNow queue to
//     detect when a dealer domain is archived for the first time (possible
//     closure signal).
//
//  2. Changelog detection: diff two Wayback snapshots of the same dealer domain
//     6 months apart to detect address changes, phone number changes, or
//     inventory wipeouts (closing signals).
//
// # Why deferred
//
// The Wayback Machine does not offer a push-based subscription API. Reactive
// monitoring requires periodic polling of the CDX API, which is already
// implemented in C.2 (wayback sub-technique). O.3's value is in the changelog
// diff logic, which depends on the document extraction pipeline (Phase 3,
// Sprint E01-E12) to reliably compare structured dealer content across snapshots.
//
// Implementing O.3 before Phase 3 extraction is available would produce only
// raw HTML diffs -- high noise, low signal.
//
// # Activation path
//
// 1. Phase 3 extraction pipeline (Sprint E01-E12) must be operational.
// 2. Implement snapshot diffing in O.3: fetch two CDX snapshots 180 days apart,
//    extract structured dealer record from each using the Phase 3 extractor,
//    diff address/phone/hours fields, classify changes as event signals.
// 3. Event types: "ADDRESS_CHANGE", "PHONE_CHANGE", "HOURS_CHANGE", "INVENTORY_WIPEOUT".
// Estimated activation sprint: Sprint 22+ (post Phase 3 extraction pipeline).
package wayback_monitor

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "O.3"
	subTechName = "Wayback Machine reactive monitoring (DEFERRED -- pending Phase 3 extraction)"
)

// WaybackMonitor is the O.3 stub.
type WaybackMonitor struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a WaybackMonitor stub.
func New(graph kg.KnowledgeGraph) *WaybackMonitor {
	return &WaybackMonitor{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (w *WaybackMonitor) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (w *WaybackMonitor) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result.
func (w *WaybackMonitor) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	w.log.Info("O.3 Wayback Monitor: DEFERRED",
		"reason", "changelog diff requires Phase 3 extraction pipeline (Sprint E01-E12); C.2 already covers CDX snapshot discovery",
		"activation", "Sprint 22+ post Phase 3; implement snapshot diffing for ADDRESS_CHANGE/PHONE_CHANGE/INVENTORY_WIPEOUT events",
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}, nil
}
