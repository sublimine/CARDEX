// Package kg provides the Knowledge Graph abstraction over the SQLite OLTP
// database that stores the dealer ecosystem.
package kg

import (
	"context"
	"time"
)

// ── Core domain types ───────────────────────────────────────────────────────

// DealerStatus represents the lifecycle state of a dealer entity.
type DealerStatus string

const (
	StatusActive     DealerStatus = "ACTIVE"
	StatusDormant    DealerStatus = "DORMANT"
	StatusClosed     DealerStatus = "CLOSED"
	StatusUnverified DealerStatus = "UNVERIFIED"
)

// IdentifierType classifies an external registry identifier.
type IdentifierType string

const (
	IdentifierVAT            IdentifierType = "VIES_VAT"
	IdentifierSIRET          IdentifierType = "SIRET"
	IdentifierSIREN          IdentifierType = "SIREN"
	IdentifierKvK            IdentifierType = "KVK"
	IdentifierBCE            IdentifierType = "BCE"
	IdentifierZefix          IdentifierType = "ZEFIX_UID"
	IdentifierHandelsregister IdentifierType = "HANDELSREGISTER"
)

// DealerEntity is the canonical representation of a B2B dealer operator.
type DealerEntity struct {
	DealerID          string
	CanonicalName     string
	NormalizedName    string
	CountryCode       string
	PrimaryVAT        *string
	LegalForm         *string
	FoundedYear       *int
	Status            DealerStatus
	OperationalScore  *float64
	ConfidenceScore   float64
	FirstDiscoveredAt time.Time
	LastConfirmedAt   time.Time
	MetadataJSON      *string
}

// DealerIdentifier is an external ID attached to a DealerEntity.
type DealerIdentifier struct {
	IdentifierID    string
	DealerID        string
	IdentifierType  IdentifierType
	IdentifierValue string
	SourceFamily    string
	ValidatedAt     *time.Time
	ValidStatus     string
}

// DealerLocation is a physical location associated with a dealer.
type DealerLocation struct {
	LocationID        string
	DealerID          string
	IsPrimary         bool
	AddressLine1      *string
	AddressLine2      *string
	PostalCode        *string
	City              *string
	Region            *string
	CountryCode       string
	Lat               *float64
	Lon               *float64
	H3Index           *string // Sprint 1: nil stub; computed in Sprint 2
	OpeningHoursJSON  *string
	SourceFamilies    string // comma-separated: "A,B,H"
}

// DiscoveryRecord is an audit entry linking a dealer to the family+sub-technique
// that discovered it.
type DiscoveryRecord struct {
	RecordID             string
	DealerID             string
	Family               string
	SubTechnique         string
	SourceURL            *string
	SourceRecordID       *string
	ConfidenceContributed float64
	DiscoveredAt         time.Time
	LastReconfirmedAt    *time.Time
}

// ── Interface ───────────────────────────────────────────────────────────────

// KnowledgeGraph is the read/write interface over the dealer Knowledge Graph.
// The production implementation is SQLiteGraph (see dealer.go).
// The in-memory mock (see kg_test.go) satisfies this interface for tests.
type KnowledgeGraph interface {
	// UpsertDealer inserts or updates a dealer entity. The implementation
	// uses the ULID dealer_id as the unique key.
	UpsertDealer(ctx context.Context, e *DealerEntity) error

	// AddIdentifier attaches an external identifier to an existing dealer.
	// Returns nil if the (type, value) pair already exists (idempotent).
	AddIdentifier(ctx context.Context, id *DealerIdentifier) error

	// AddLocation attaches a physical location to a dealer.
	AddLocation(ctx context.Context, loc *DealerLocation) error

	// RecordDiscovery writes a discovery audit entry.
	RecordDiscovery(ctx context.Context, rec *DiscoveryRecord) error

	// FindDealerByIdentifier returns the dealer_id for the given (type, value)
	// pair, or ("", nil) if not found.
	FindDealerByIdentifier(ctx context.Context, idType IdentifierType, idValue string) (string, error)
}
