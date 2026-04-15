package pipeline

import "context"

// Priority constants for the extraction cascade. Higher value = attempted first.
//
// Final Phase 3 ordering:
//
//	E12 (1500) Edge push — dealer-trusted signed source, highest confidence
//	E01 (1200) JSON-LD Schema.org
//	E02 (1100) CMS REST endpoint
//	E05 (950)  DMS hosted API
//	E03 (1000) Sitemap XML
//	E04 (900)  RSS/Atom feeds
//	E06 (850)  Microdata/RDFa
//	E07 (800)  Playwright XHR interception
//	E08 (700)  PDF catalog parsing
//	E09 (700)  Excel/CSV feeds
//	E10 (600)  Email-based inventory
//	E11 (100)  Manual review queue
const (
	PriorityE12 = 1500 // Edge push (Tauri client) — dealer-signed, highest trust
	PriorityE01 = 1200 // JSON-LD Schema.org
	PriorityE02 = 1100 // CMS REST endpoint
	PriorityE03 = 1000 // Sitemap XML
	PriorityE05 = 950  // DMS hosted API
	PriorityE04 = 900  // RSS/Atom feeds
	PriorityE06 = 850  // Microdata/RDFa
	PriorityE07 = 800  // XHR/AJAX discovery (Playwright)
	PriorityE08 = 700  // PDF catalog parsing
	PriorityE09 = 700  // CSV/Excel feeds
	PriorityE10 = 600  // Email-based inventory
	PriorityE11 = 100  // Manual review queue (last resort)
)

// ExtractionStrategy is the interface all strategies E01-E12 must implement.
// The orchestrator operates exclusively through this interface, enabling
// strategy composition without modification of orchestrator code.
type ExtractionStrategy interface {
	// ID returns the canonical identifier ("E01", "E02", ...).
	ID() string

	// Name returns the human-readable strategy name.
	Name() string

	// Applicable performs a fast O(1) pre-check (no network I/O) to determine
	// whether this strategy is a candidate for the given dealer.
	// Called by the orchestrator before Extract.
	Applicable(dealer Dealer) bool

	// Extract executes the full extraction for the dealer.
	// Must respect ctx.Done() for cancellation.
	// Must never perform I/O that violates robots.txt or dealer ToS.
	Extract(ctx context.Context, dealer Dealer) (*ExtractionResult, error)

	// Priority returns the cascade ordering value. Higher = attempted first.
	Priority() int
}

// Storage persists extraction results to the shared Knowledge Graph database.
// Defined here so pipeline.go can reference it without circular imports.
type Storage interface {
	// PersistVehicles upserts vehicle records for the given dealer.
	// Returns the count of new records inserted.
	PersistVehicles(ctx context.Context, dealerID string, vehicles []*VehicleRaw) (int, error)

	// ListPendingDealers returns dealers whose next_extraction_at is past-due.
	ListPendingDealers(ctx context.Context, limit int) ([]Dealer, error)

	// MarkExtractionDone records that extraction ran for a dealer, updating
	// next_extraction_at based on the strategy's recheck interval.
	MarkExtractionDone(ctx context.Context, dealerID, strategyID string) error

	// DealerExists returns true if the dealer_id exists in dealer_entity.
	DealerExists(ctx context.Context, dealerID string) (bool, error)

	// Close releases the database connection.
	Close() error
}
