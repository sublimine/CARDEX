// Package e10_email implements extraction strategy E10 — Email-Based Inventory.
//
// # Architecture
//
// Some micro-dealers have no website feed; they send inventory updates via email
// with a CSV or Excel attachment. This strategy acts as the extraction side of
// a larger email-ingestion pipeline:
//
//  1. Dealer sends email with CSV/Excel attachment to inventory@cardex.eu.
//  2. An IMAP poller (separate service, outside extraction module) fetches new
//     messages every hour and places attachments into a staging table
//     `email_inventory_staging(dealer_id, filename, content, received_at)`.
//  3. E10.Extract reads from that staging table, delegates parsing to the
//     same logic used by E09 (Excel/CSV), then marks rows as processed.
//  4. Sender email ↔ dealer matching uses dealer_entity.contact_email.
//
// # Implementation status
//
// Skeleton: interface definition, Applicable logic, and an Extract stub that
// signals "awaiting attachment" when no staging rows are present.
// The real IMAP poller and staging table wiring are Phase 4 work.
//
// Priority: 200.
package e10_email

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E10"
	strategyName = "Email-Based Inventory"
)

// EmailInventoryReader is the interface for reading parsed email attachments
// from the staging table. Implement with a real DB-backed reader in Phase 4.
type EmailInventoryReader interface {
	// ReadPendingVehicles returns vehicles from email attachments not yet consumed
	// for the given dealer. Returns nil, nil when no pending rows exist.
	ReadPendingVehicles(ctx context.Context, dealerID string) ([]*pipeline.VehicleRaw, error)
	// MarkConsumed marks all staged rows for the dealer as processed.
	MarkConsumed(ctx context.Context, dealerID string) error
}

// noOpReader is the default reader used when no staging table is wired.
type noOpReader struct{}

func (n *noOpReader) ReadPendingVehicles(_ context.Context, _ string) ([]*pipeline.VehicleRaw, error) {
	return nil, nil
}
func (n *noOpReader) MarkConsumed(_ context.Context, _ string) error { return nil }

// Email is the E10 extraction strategy.
type Email struct {
	reader EmailInventoryReader
	log    *slog.Logger
}

// New constructs an Email strategy with no-op staging reader.
// Inject a real EmailInventoryReader via NewWithReader when the staging
// table is available (Phase 4).
func New() *Email {
	return NewWithReader(&noOpReader{})
}

// NewWithReader constructs an Email strategy with the given staging reader.
func NewWithReader(r EmailInventoryReader) *Email {
	return &Email{
		reader: r,
		log:    slog.Default().With("strategy", strategyID),
	}
}

func (e *Email) ID() string    { return strategyID }
func (e *Email) Name() string  { return strategyName }
func (e *Email) Priority() int { return pipeline.PriorityE10 }

// Applicable returns true for dealers with the "email_inventory" hint or
// those whose contact_email is set (suggesting email-based onboarding).
func (e *Email) Applicable(dealer pipeline.Dealer) bool {
	for _, hint := range dealer.ExtractionHints {
		if hint == "email_inventory" || strings.HasPrefix(hint, "contact_email:") {
			return true
		}
	}
	return false
}

// Extract reads pending vehicles from the email-attachment staging table.
// Returns an informational error when no staging data is available yet.
func (e *Email) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	vehicles, err := e.reader.ReadPendingVehicles(ctx, dealer.ID)
	if err != nil {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "EMAIL_READER_ERROR",
			Message: err.Error(),
		})
		return result, nil
	}

	if len(vehicles) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_EMAIL_ATTACHMENT",
			Message: "no pending email attachment in staging table — dealer must send inventory CSV/XLSX to inventory@cardex.eu",
		})
		return result, nil
	}

	result.Vehicles = vehicles
	_ = e.reader.MarkConsumed(ctx, dealer.ID)
	return result, nil
}
