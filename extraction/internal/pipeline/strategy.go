package pipeline

import "context"

// Priority constants for the extraction cascade. Higher value = attempted first.
//
// Ordering matches planning/04_EXTRACTION_PIPELINE/INTERFACES.md:241-254.
// After the E11↔E12 semantic alignment (E11=Edge, E12=Manual):
//
//	E11 (1500) Edge push — dealer-trusted signed source, highest confidence
//	E01 (1200) JSON-LD Schema.org
//	E02 (1100) CMS REST endpoint
//	E05 (1050) DMS hosted API
//	E03 (1000) Sitemap XML
//	E04 (900)  RSS/Atom feeds
//	E06 (800)  Microdata/RDFa
//	E07 (700)  Playwright XHR interception
//	E09 (400)  Excel/CSV feeds
//	E08 (300)  PDF catalog parsing
//	E10 (200)  Email-based inventory
//	E13 (100)  VLM Screenshot Vision (last automated, opt-in)
//	E12 (0)    Manual review queue (last resort)
const (
	PriorityE11 = 1500 // Edge push (Tauri client) — dealer-signed, highest trust
	PriorityE01 = 1200 // JSON-LD Schema.org
	PriorityE02 = 1100 // CMS REST endpoint
	PriorityE05 = 1050 // DMS hosted API
	PriorityE03 = 1000 // Sitemap XML
	PriorityE04 = 900  // RSS/Atom feeds
	PriorityE06 = 800  // Microdata/RDFa
	PriorityE07 = 700  // XHR/AJAX discovery (Playwright)
	PriorityE09 = 400  // CSV/Excel feeds
	PriorityE08 = 300  // PDF catalog parsing
	PriorityE10 = 200  // Email-based inventory
	PriorityE13 = 100  // VLM Screenshot Vision (last automated, before E12 manual)
	PriorityE12 = 0    // Manual review queue (last resort)
)

// ExtractionStrategy is the interface all strategies E01-E13 must implement.
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
