// Package e12_manual implements extraction strategy E12 — Manual Review Queue.
//
// # Strategy
//
// When all automated strategies E01–E10 fail to yield vehicles for a dealer,
// E12 acts as the final safety net: it enqueues the dealer for human review
// and records that no automated extraction path was found.
//
// # Architecture
//
// E12 writes to a `manual_review_queue` table:
//
//	CREATE TABLE IF NOT EXISTS manual_review_queue (
//	    dealer_id    TEXT PRIMARY KEY,
//	    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|in_progress|done
//	    assigned_to  TEXT,
//	    notes        TEXT,
//	    vehicle_count INTEGER DEFAULT 0,
//	    last_updated  DATETIME DEFAULT CURRENT_TIMESTAMP
//	);
//
// A Cardex analyst uses the admin UI (POST /admin/manual-review/{dealer_id}/vehicles)
// to submit vehicles for that dealer; those are persisted via the normal pipeline.
//
// # Phase 4 work
//
// Skeleton + ManualQueueWriter interface. The real SQLite-backed implementation
// is wired in main.go during Phase 4. The strategy itself is fully functional.
//
// Priority: 0 (last resort — runs only when all automated strategies failed).
package e12_manual

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E12"
	strategyName = "Manual Review Queue"
)

// ManualQueueWriter persists a dealer into the manual review queue.
// Implement with a DB-backed writer in the admin/storage layer.
type ManualQueueWriter interface {
	EnqueueDealer(ctx context.Context, dealerID string) error
}

// noOpWriter is the default no-op used when no queue store is wired.
type noOpWriter struct{}

func (n *noOpWriter) EnqueueDealer(_ context.Context, _ string) error { return nil }

// Manual is the E12 extraction strategy.
type Manual struct {
	queue ManualQueueWriter
	log   *slog.Logger
}

// New constructs a Manual strategy with a no-op queue writer.
// Inject a real ManualQueueWriter via NewWithQueue for production use.
func New() *Manual {
	return NewWithQueue(&noOpWriter{})
}

// NewWithQueue constructs a Manual strategy with the given queue writer.
func NewWithQueue(q ManualQueueWriter) *Manual {
	return &Manual{
		queue: q,
		log:   slog.Default().With("strategy", strategyID),
	}
}

func (e *Manual) ID() string    { return strategyID }
func (e *Manual) Name() string  { return strategyName }
func (e *Manual) Priority() int { return pipeline.PriorityE12 }

// Applicable returns true for all dealers — E12 is the universal fallback.
func (e *Manual) Applicable(_ pipeline.Dealer) bool { return true }

// Extract enqueues the dealer for manual review and returns an informational
// result indicating that human review is required.
func (e *Manual) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	if err := e.queue.EnqueueDealer(ctx, dealer.ID); err != nil {
		e.log.Warn("E12: failed to enqueue dealer for manual review",
			"dealer_id", dealer.ID,
			"domain", dealer.Domain,
			"err", err,
		)
	} else {
		e.log.Info("E12: dealer enqueued for manual review",
			"dealer_id", dealer.ID,
			"domain", dealer.Domain,
		)
	}

	result.Errors = append(result.Errors, pipeline.ExtractionError{
		Code:    "MANUAL_REVIEW_REQUIRED",
		Message: "no automated extraction path found — dealer queued for human review",
	})
	return result, nil
}
