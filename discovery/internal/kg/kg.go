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
	IdentifierBORMEAct        IdentifierType = "BORME_ACT"  // BORME announcement ID: BORME-A-YYYY-NNN-NN
	IdentifierKBO             IdentifierType = "KBO_BCE"    // Belgian KBO/BCE enterprise number: NNNN.NNN.NNN

	// Familia B — geocartografía
	IdentifierOSMID       IdentifierType = "OSM_ID"       // OpenStreetMap element: "node/12345678" or "way/12345678"
	IdentifierWikidataQID IdentifierType = "WIKIDATA_QID" // Wikidata entity: "Q12345"

	// Familia C — cartografía web
	IdentifierDomainCT IdentifierType = "DOMAIN_FROM_CT" // Domain discovered via Certificate Transparency logs

	// ── Family F — aggregator marketplace identifiers ────────────────────────
	IdentifierMobileDeID      IdentifierType = "MOBILE_DE_ID"       // mobile.de dealer profile slug/ID
	IdentifierLaCentraleProID IdentifierType = "LACENTRALE_PRO_ID"  // La Centrale garage/pro directory ID
	IdentifierAutoScout24ID   IdentifierType = "AUTOSCOUT24_ID"     // AutoScout24 dealer account ID (pan-EU)

	// ── Family G — sectoral association member identifiers ───────────────────
	IdentifierMemberBOVAG   IdentifierType = "MEMBER_BOVAG"    // BOVAG (NL) member number or slug
	IdentifierMemberZDK     IdentifierType = "MEMBER_ZDK"      // ZDK (DE) member ID — deferred Sprint 7+
	IdentifierMemberMobilians IdentifierType = "MEMBER_MOBILIANS" // Mobilians (FR) member ID — deferred Sprint 7+
	IdentifierMemberFaconauto IdentifierType = "MEMBER_FACONAUTO" // FACONAUTO (ES) member ID — deferred Sprint 7+
	IdentifierMemberTraxio  IdentifierType = "MEMBER_TRAXIO"   // TRAXIO (BE) member ID — deferred Sprint 7+
	IdentifierMemberAGVS    IdentifierType = "MEMBER_AGVS_UPSA" // AGVS-UPSA (CH) member ID — deferred Sprint 7+

	// ── Family H — OEM dealer network identifiers ────────────────────────────
	// Value format: "{oem_brand}:{dealer_id}" to avoid cross-brand collisions.
	// e.g. "VW:DE-12345", "BMW:DE-67890", "TOYOTA:DE-99001"
	IdentifierOEMDealerID IdentifierType = "OEM_DEALER_ID" // OEM official dealer ID — deferred Sprint 7+
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
	Phone             *string // optional phone number — added by Sprint 5 migration v3
	SourceFamilies    string  // comma-separated: "A,B,H"
}

// DealerWebPresence is a known web domain presence for a dealer entity,
// backed by the dealer_web_presence table.
type DealerWebPresence struct {
	WebID                string
	DealerID             string
	Domain               string
	URLRoot              string
	PlatformType         *string
	DMSProvider          *string
	ExtractionStrategy   *string
	DiscoveredByFamilies string
	MetadataJSON         *string // nullable — added by Sprint 4 migration v2
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

	// ── Web presence ────────────────────────────────────────────────────────

	// UpsertWebPresence adds or updates a dealer web presence entry.
	// The domain column is the unique natural key.
	UpsertWebPresence(ctx context.Context, wp *DealerWebPresence) error

	// FindDealerIDByDomain returns the dealer_id for the given domain,
	// or ("", nil) if no web presence entry exists for that domain.
	FindDealerIDByDomain(ctx context.Context, domain string) (string, error)

	// UpdateWebPresenceMetadata overwrites the metadata_json field for the
	// given domain. Returns an error if the domain is not found.
	UpdateWebPresenceMetadata(ctx context.Context, domain, metadataJSON string) error

	// ListWebPresencesByCountry returns all web presence entries for dealers
	// whose country_code matches the given ISO 3166-1 alpha-2 code.
	ListWebPresencesByCountry(ctx context.Context, country string) ([]*DealerWebPresence, error)
}
