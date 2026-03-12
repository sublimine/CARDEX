// Package cascade implements the L1 -> L2 -> L3 tax classification cascade.
//
// Resolution order:
//   L1: Redis HGET exact match (dict:l1_tax)        - 0.001ms, 0% CPU
//   L2: HNSW vector search (Nomic embeddings)        - <2ms, <1% CPU
//   L3: Qwen2.5-7B with GBNF grammar (async stream)  - <3s, ~50% of 8 cores
//
// FAIL-CLOSED: Any result with confidence < 0.95 becomes REQUIRES_HUMAN_AUDIT.
package cascade

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/redis/go-redis/v9"

	"cardex/neural/internal/l1"
	"cardex/neural/internal/l2"
)

const (
	ConfidenceThreshold = 0.95
	L3PendingStream     = "stream:l3_pending"
)

// Verdict is the final classification result from the cascade.
type Verdict struct {
	TaxStatus  string
	Confidence float64
	Tier       string // "L1", "L2", "L3_PENDING", "OVERRIDE"
	Source     string // L2: source ULID that matched
}

// VehicleInput contains data needed for classification.
type VehicleInput struct {
	VehicleULID string
	Source      string
	Description string
	SellerType  string
	SellerVATID string
	Country     string
}

// Classifier runs the L1 -> L2 -> L3 cascade.
type Classifier struct {
	l1Cache *l1.Cache
	l2Store *l2.Store
	rdb     *redis.Client
	l2Ready bool
}

// NewClassifier creates a cascade classifier.
// l2Store can be nil if RediSearch is unavailable (degrades to L1 -> L3).
func NewClassifier(rdb *redis.Client, l1Cache *l1.Cache, l2Store *l2.Store) *Classifier {
	return &Classifier{
		l1Cache: l1Cache,
		l2Store: l2Store,
		rdb:     rdb,
		l2Ready: l2Store != nil,
	}
}

// Classify runs the cascade for a vehicle.
func (c *Classifier) Classify(ctx context.Context, input VehicleInput) Verdict {
	// HARD OVERRIDE: Private seller -> REBU unconditionally
	if input.SellerType == "PRIVATE" {
		slog.Info("cascade: PRIVATE seller override",
			"vehicle", input.VehicleULID, "status", "REBU")
		return Verdict{TaxStatus: "REBU", Confidence: 1.0, Tier: "OVERRIDE"}
	}

	// L1: Exact match
	if r, ok := c.l1Cache.Get(ctx, input.VehicleULID); ok {
		status := r.TaxStatus
		if r.Confidence < ConfidenceThreshold {
			status = "REQUIRES_HUMAN_AUDIT"
		}
		slog.Debug("cascade: L1 hit",
			"vehicle", input.VehicleULID, "status", status, "confidence", r.Confidence)
		return Verdict{TaxStatus: status, Confidence: r.Confidence, Tier: "L1"}
	}

	// L2: Vector similarity
	if c.l2Ready {
		if r, ok := c.l2Store.Search(ctx, input.Description); ok {
			status := r.TaxStatus
			if r.Confidence < ConfidenceThreshold {
				status = "REQUIRES_HUMAN_AUDIT"
			}
			// Promote to L1 for instant next lookup
			_ = c.l1Cache.Set(ctx, input.VehicleULID, l1.Result{
				TaxStatus: r.TaxStatus, Confidence: r.Confidence,
			})
			return Verdict{
				TaxStatus: status, Confidence: r.Confidence,
				Tier: "L2", Source: r.SourceULID,
			}
		}
	}

	// L3: Dispatch to Qwen2.5 async worker
	c.dispatchL3(ctx, input)
	return Verdict{TaxStatus: "REQUIRES_HUMAN_AUDIT", Confidence: 0.0, Tier: "L3_PENDING"}
}

func (c *Classifier) dispatchL3(ctx context.Context, input VehicleInput) {
	err := c.rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: L3PendingStream,
		Values: map[string]interface{}{
			"vehicle_ulid": input.VehicleULID,
			"source":       input.Source,
			"description":  truncate(input.Description, 500),
			"seller_type":  input.SellerType,
			"seller_vat":   input.SellerVATID,
			"country":      input.Country,
		},
	}).Err()
	if err != nil {
		slog.Error("cascade: L3 dispatch failed",
			"vehicle", input.VehicleULID, "error", err)
	}
}

// ApplyL3Result is called by the L3 worker after classification.
func (c *Classifier) ApplyL3Result(ctx context.Context, vehicleULID string, description string, taxStatus string, confidence float64) error {
	effectiveStatus := taxStatus
	if confidence < ConfidenceThreshold {
		effectiveStatus = "REQUIRES_HUMAN_AUDIT"
	}

	err := c.l1Cache.Set(ctx, vehicleULID, l1.Result{
		TaxStatus: effectiveStatus, Confidence: confidence,
	})
	if err != nil {
		return fmt.Errorf("cascade: L1 update: %w", err)
	}

	if c.l2Ready && description != "" {
		if err := c.l2Store.Index(ctx, vehicleULID, description, effectiveStatus, confidence); err != nil {
			slog.Warn("cascade: L2 index failed (non-fatal)", "vehicle", vehicleULID, "error", err)
		}
	}

	return nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
