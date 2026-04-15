// Package e12_edge implements extraction strategy E12 — Edge Dealer Push.
//
// # Architecture
//
// E12 is the highest-priority strategy (1500) because data pushed directly by
// the dealer from their local DMS is the most trustworthy source — no
// scraping, no heuristics, no field mapping ambiguity.
//
// # Deployment model
//
// Dealers install a free Tauri desktop client on the same machine as their
// DMS software (CDK Global, Reynolds & Reynolds, etc.). The client reads the
// DMS database, serialises vehicle records to protobuf, and pushes them via
// signed gRPC to this service at configurable intervals.
//
// # gRPC server (Sprint 18 skeleton)
//
// The proto service definition lives at:
//   extraction/internal/extractor/e12_edge/proto/edge.proto
//
// The actual gRPC server (code-generated from the proto, with JWT auth
// middleware) is Phase 4 work. This sprint delivers:
//   - The ExtractionStrategy wrapper (E12) that reads from a staging table.
//   - The EdgeInventoryStore interface for the staging table interaction.
//   - A no-op store implementation for use in main.go until Phase 4 wires
//     the real gRPC receiver.
//
// # Data flow
//
//  1. gRPC server receives PushInventoryRequest from Tauri client.
//  2. Server authenticates dealer JWT, validates VINs, writes vehicles to
//     `edge_inventory_staging(push_id, dealer_id, vehicles_json, received_at)`.
//  3. Orchestrator runs E12.Extract(dealer) on schedule.
//  4. E12 reads from staging, converts to VehicleRaw, marks push consumed.
//
// Priority: 1500 (highest — dealer-signed trusted source).
package e12_edge

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E12"
	strategyName = "Edge Push (Tauri)"
)

// EdgeInventoryStore provides access to the gRPC push staging table.
// The real implementation reads from `edge_inventory_staging` and marks
// consumed rows. Inject via NewWithStore.
type EdgeInventoryStore interface {
	// ReadPendingPush returns vehicles from unconsumed edge pushes for the dealer.
	ReadPendingPush(ctx context.Context, dealerID string) ([]*pipeline.VehicleRaw, error)
	// MarkConsumed marks the dealer's pending push as consumed.
	MarkConsumed(ctx context.Context, dealerID string) error
}

// noOpStore is the default store used until the gRPC server is wired (Phase 4).
type noOpStore struct{}

func (n *noOpStore) ReadPendingPush(_ context.Context, _ string) ([]*pipeline.VehicleRaw, error) {
	return nil, nil
}
func (n *noOpStore) MarkConsumed(_ context.Context, _ string) error { return nil }

// Edge is the E12 extraction strategy.
type Edge struct {
	store EdgeInventoryStore
	log   *slog.Logger
}

// New constructs an Edge strategy with a no-op staging store.
// Replace with NewWithStore when the gRPC push receiver is operational.
func New() *Edge {
	return NewWithStore(&noOpStore{})
}

// NewWithStore constructs an Edge strategy with the given staging store.
func NewWithStore(s EdgeInventoryStore) *Edge {
	return &Edge{
		store: s,
		log:   slog.Default().With("strategy", strategyID),
	}
}

func (e *Edge) ID() string    { return strategyID }
func (e *Edge) Name() string  { return strategyName }
func (e *Edge) Priority() int { return pipeline.PriorityE12 }

// Applicable returns true for dealers with the "edge_client_registered" hint,
// indicating they have an active Tauri client installation.
func (e *Edge) Applicable(dealer pipeline.Dealer) bool {
	for _, hint := range dealer.ExtractionHints {
		if hint == "edge_client_registered" {
			return true
		}
	}
	return false
}

// Extract reads vehicles from the edge push staging table and returns them.
func (e *Edge) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	vehicles, err := e.store.ReadPendingPush(ctx, dealer.ID)
	if err != nil {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "EDGE_STORE_ERROR",
			Message: err.Error(),
		})
		return result, nil
	}

	if len(vehicles) == 0 {
		// No pending push — not an error, just nothing new since last check.
		return result, nil
	}

	result.Vehicles = vehicles
	result.SourceCount = 1

	if err := e.store.MarkConsumed(ctx, dealer.ID); err != nil {
		e.log.Warn("E12: failed to mark push as consumed",
			"dealer_id", dealer.ID,
			"err", err,
		)
	}

	e.log.Info("E12: edge push consumed",
		"dealer_id", dealer.ID,
		"vehicles", len(vehicles),
	)
	return result, nil
}
