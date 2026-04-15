// Package kg provides the Knowledge Graph abstraction over the SQLite OLTP
// database that stores the dealer ecosystem.
package kg

import (
	"context"
	"time"
)

// -- Core domain types -------------------------------------------------------

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
	IdentifierVAT             IdentifierType = "VIES_VAT"
	IdentifierSIRET           IdentifierType = "SIRET"
	IdentifierSIREN           IdentifierType = "SIREN"
	IdentifierKvK             IdentifierType = "KVK"
	IdentifierBCE             IdentifierType = "BCE"
	IdentifierZefix           IdentifierType = "ZEFIX_UID"
	IdentifierHandelsregister IdentifierType = "HANDELSREGISTER"
	IdentifierBORMEAct        IdentifierType = "BORME_ACT" // BORME announcement ID: BORME-A-YYYY-NNN-NN
	IdentifierKBO             IdentifierType = "KBO_BCE"   // Belgian KBO/BCE enterprise number: NNNN.NNN.NNN

	// Familia B -- geocartografia
	IdentifierOSMID       IdentifierType = "OSM_ID"       // OpenStreetMap element: "node/12345678" or "way/12345678"
	IdentifierWikidataQID IdentifierType = "WIKIDATA_QID" // Wikidata entity: "Q12345"

	// Familia C -- cartografia web
	IdentifierDomainCT IdentifierType = "DOMAIN_FROM_CT" // Domain discovered via Certificate Transparency logs

	// -- Family F -- aggregator marketplace identifiers ------------------------
	IdentifierMobileDeID      IdentifierType = "MOBILE_DE_ID"      // mobile.de dealer profile slug/ID
	IdentifierLaCentraleProID IdentifierType = "LACENTRALE_PRO_ID" // La Centrale garage/pro directory ID
	IdentifierAutoScout24ID   IdentifierType = "AUTOSCOUT24_ID"    // AutoScout24 dealer account ID (pan-EU)

	// -- Family G -- sectoral association member identifiers -------------------
	IdentifierMemberBOVAG    IdentifierType = "MEMBER_BOVAG"     // BOVAG (NL) member number or slug
	IdentifierMemberZDK      IdentifierType = "MEMBER_ZDK"       // ZDK (DE) member ID -- deferred Sprint 7+
	IdentifierMemberMobilians IdentifierType = "MEMBER_MOBILIANS" // Mobilians (FR) member ID -- deferred Sprint 7+
	IdentifierMemberFaconauto IdentifierType = "MEMBER_FACONAUTO" // FACONAUTO (ES) member ID -- deferred Sprint 7+
	IdentifierMemberTraxio   IdentifierType = "MEMBER_TRAXIO"    // TRAXIO (BE) member ID -- deferred Sprint 7+
	IdentifierMemberAGVS     IdentifierType = "MEMBER_AGVS_UPSA" // AGVS-UPSA (CH) member ID -- deferred Sprint 7+

	// -- Family H -- OEM dealer network identifiers ---------------------------
	// Value format: "{oem_brand}:{dealer_id}" to avoid cross-brand collisions.
	// e.g. "VW:DE-12345", "BMW:DE-67890", "TOYOTA:DE-99001"
	IdentifierOEMDealerID IdentifierType = "OEM_DEALER_ID" // OEM official dealer ID -- deferred Sprint 7+

	// -- Family I -- inspection & certification network identifiers -----------
	// Inspection stations are NOT dealer candidates (is_dealer_candidate=false).
	// They are adjacent signals used to cross-reference dealer operators that also
	// hold inspection authorisations.
	IdentifierAPKStationID      IdentifierType = "APK_STATION_ID"       // RDW APK (NL) erkenningsnummer
	IdentifierDEKRAStationID    IdentifierType = "DEKRA_STATION_ID"     // DEKRA station ID (DE/FR/...)
	IdentifierTUVStationID      IdentifierType = "TUV_STATION_ID"       // TUV station ID (DE, multiple orgs)
	IdentifierITVStationID      IdentifierType = "ITV_STATION_ID"       // ITV station ID (ES)
	IdentifierCTStationID       IdentifierType = "CT_STATION_ID"        // Controle Technique station ID (FR/BE)
	IdentifierBoschCarServiceID IdentifierType = "BOSCH_CAR_SERVICE_ID" // Bosch Car Service partner ID (pan-EU)
	IdentifierMFKStationID      IdentifierType = "MFK_STATION_ID"       // MFK station ID (CH)

	// -- Family K -- alternative search engine identifiers --------------------
	IdentifierDomainFromSearch IdentifierType = "DOMAIN_FROM_SEARCH" // domain discovered via SearXNG/Marginalia

	// -- Family M -- fiscal signal identifiers --------------------------------
	IdentifierVATValidatedVIES IdentifierType = "VAT_VALIDATED_VIES" // VIES-confirmed VAT number
	IdentifierUIDValidatedCH   IdentifierType = "UID_VALIDATED_CH"   // Swiss UID-Register confirmed UID

	// -- Family L -- social profile identifiers --------------------------------
	// Value format: platform-native ID or handle.
	IdentifierLinkedInCompanyID IdentifierType = "LINKEDIN_COMPANY_ID" // LinkedIn company slug or numeric ID
	IdentifierYouTubeChannelID  IdentifierType = "YOUTUBE_CHANNEL_ID"  // YouTube channel ID (UC...)
	IdentifierGooglePlaceID     IdentifierType = "GOOGLE_PLACE_ID"     // Google Maps Place ID (ChIJ...)

	// -- Family J -- sub-jurisdiction / regional registry identifiers ----------
	IdentifierPappersID IdentifierType = "PAPPERS_ID" // Pappers.fr company ID (SIREN/SIRET enriched)

	// -- Family N -- infrastructure intelligence identifiers -------------------
	IdentifierCensysHostID      IdentifierType = "CENSYS_HOST_ID"       // Censys host IPv4/v6 address
	IdentifierShodanHostID      IdentifierType = "SHODAN_HOST_ID"       // Shodan host IP address
	IdentifierDNSDumpsterDomain IdentifierType = "DNSDUMPSTER_DOMAIN"   // subdomain discovered via DNSDumpster

	// -- Family O -- press archive identifiers ---------------------------------
	IdentifierGDELTArticleID IdentifierType = "GDELT_ARTICLE_ID" // GDELT article URL (event evidence)
	IdentifierRSSItemID      IdentifierType = "RSS_ITEM_ID"      // RSS feed item URL (event evidence)
)

// DealerVATCandidate is a lightweight projection of dealer_entity used for
// VAT validation batch runs (Family M). It omits heavy fields not needed during
// the validation loop.
type DealerVATCandidate struct {
	DealerID        string
	PrimaryVAT      string // non-null guaranteed by the query filter
	CountryCode     string
	CanonicalName   string
	ConfidenceScore float64
}

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
	LocationID       string
	DealerID         string
	IsPrimary        bool
	AddressLine1     *string
	AddressLine2     *string
	PostalCode       *string
	City             *string
	Region           *string
	CountryCode      string
	Lat              *float64
	Lon              *float64
	H3Index          *string // Sprint 1: nil stub; computed in Sprint 2
	OpeningHoursJSON *string
	Phone            *string // optional phone number -- added by Sprint 5 migration v3
	SourceFamilies   string  // comma-separated: "A,B,H"
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
	MetadataJSON         *string // nullable -- added by Sprint 4 migration v2
	// Sprint 12 -- Family D CMS fingerprinting (migration v6)
	CMSFingerprintJSON  *string // {"cms":"wordpress","version":"6.4","confidence":0.85}
	CMSScannedAt        *time.Time
	ExtractionHintsJSON *string // {"endpoints":[...],"plugins":["vehicle-manager"]}
}

// DealerSocialProfile is a social media or directory profile linked to a dealer.
// Backed by the dealer_social_profile table.
type DealerSocialProfile struct {
	ProfileID            string
	DealerID             string
	Platform             string // "youtube", "linkedin", "google_maps"
	ProfileURL           string
	ExternalID           *string
	Rating               *float64
	ReviewCount          *int
	LastActivityDetected *time.Time
	MetadataJSON         *string
}

// DiscoveryRecord is an audit entry linking a dealer to the family+sub-technique
// that discovered it.
type DiscoveryRecord struct {
	RecordID              string
	DealerID              string
	Family                string
	SubTechnique          string
	SourceURL             *string
	SourceRecordID        *string
	ConfidenceContributed float64
	DiscoveredAt          time.Time
	LastReconfirmedAt     *time.Time
}

// DealerPressSignal is a press article mention linked to a dealer entity.
// Backed by the dealer_press_signal table (migration v7).
type DealerPressSignal struct {
	SignalID     string
	DealerID     string
	EventType    string    // "OPENING", "CLOSING", "MERGER", "SALE", "MENTION"
	ArticleURL   string
	ArticleTitle string
	SourceFamily string    // sub-technique ID: "O.1" or "O.2"
	DetectedAt   time.Time
}

// HostIPCluster groups dealer IDs sharing the same IPv4/IPv6 host address,
// as discovered by N.1 (Censys) or N.2 (Shodan). Used by E.3 DMS clustering.
type HostIPCluster struct {
	HostIP    string
	DealerIDs []string
	Source    string // "CENSYS_HOST_ID" or "SHODAN_HOST_ID"
}

// DealerProvinceCandidate is a lightweight projection used by Family J province/
// gewest classifiers. It carries only the fields needed to derive sub-region.
type DealerProvinceCandidate struct {
	DealerID    string
	PostalCode  *string // primary location postal code (may be nil)
	City        *string // primary location city
	CountryCode string
}

// WebPresence is a minimal web-domain projection used by Family K UpsertDomainCandidate.
type WebPresence struct {
	Domain   string
	DealerID string
}

// -- Interface ----------------------------------------------------------------

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

	// -- Web presence ----------------------------------------------------------

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

	// -- Family D -- CMS fingerprinting ----------------------------------------

	// ListWebPresencesForCMSScan returns web presences for the given country
	// where cms_scanned_at IS NULL or older than staleDays days. Limit caps
	// the batch size.
	ListWebPresencesForCMSScan(ctx context.Context, country string, staleDays, limit int) ([]*DealerWebPresence, error)

	// UpsertWebTechnology stores CMS fingerprint and extraction hints for a
	// domain. Sets cms_scanned_at = now(). Identified by domain (unique key).
	UpsertWebTechnology(ctx context.Context, domain, cmsFingerprintJSON, extractionHintsJSON string) error

	// -- Family L -- social profiles -------------------------------------------

	// UpsertSocialProfile inserts or updates a social profile record.
	// Identified by (dealer_id, platform, external_id).
	UpsertSocialProfile(ctx context.Context, profile *DealerSocialProfile) error

	// -- Family M -- VAT validation --------------------------------------------

	// FindDealersForVATValidation returns dealers that have a primary_vat set
	// and whose VAT validation is either missing or older than staleDays days.
	// Only dealers whose country_code is in the countries list are returned.
	FindDealersForVATValidation(ctx context.Context, countries []string, staleDays int) ([]*DealerVATCandidate, error)

	// UpdateVATValidation writes the vat_validated_at timestamp and
	// vat_valid_status (e.g. "VALID", "INVALID", "NOT_FOUND", "ERROR") for the
	// given dealer.
	UpdateVATValidation(ctx context.Context, dealerID string, validatedAt time.Time, status string) error

	// UpdateConfidenceScore overwrites the confidence_score for the given dealer.
	// Used by M.1/M.2 to bump score when VAT is confirmed valid.
	UpdateConfidenceScore(ctx context.Context, dealerID string, score float64) error

	// -- Family K -- search signal / state ------------------------------------

	// GetProcessingState returns the value stored under key, or ("", nil) if absent.
	GetProcessingState(ctx context.Context, key string) (string, error)

	// SetProcessingState upserts the value for key with the current timestamp.
	SetProcessingState(ctx context.Context, key, value string) error

	// -- Family J -- sub-jurisdiction / regional enrichment -------------------

	// ListDealersByCountry returns a lightweight projection of all dealers for the
	// given country, used by J.NL.1 and J.BE.1 province/gewest classifiers.
	ListDealersByCountry(ctx context.Context, country string) ([]*DealerProvinceCandidate, error)

	// UpdateDealerSubRegion writes the sub_region field on dealer_location rows
	// belonging to the given dealer. Used by J.NL.1/J.BE.1 classifiers.
	UpdateDealerSubRegion(ctx context.Context, dealerID, subRegion string) error

	// -- Family N -- infrastructure intelligence ------------------------------

	// ListWebPresencesForInfraScan returns web presences for the given country
	// ordered by web_id. Limit caps the batch size.
	ListWebPresencesForInfraScan(ctx context.Context, country string, limit int) ([]*DealerWebPresence, error)

	// -- Family O -- press archive signals ------------------------------------

	// RecordPressSignal inserts a press article mention for a dealer.
	// Idempotent: duplicate signal_id is silently ignored.
	RecordPressSignal(ctx context.Context, sig *DealerPressSignal) error

	// FindDealersByName returns dealer IDs whose normalized_name exactly matches
	// the given string for the given country. Used by the O NER pipeline.
	FindDealersByName(ctx context.Context, normalizedName, country string) ([]string, error)

	// -- Family E -- DMS infrastructure mapping --------------------------------

	// SetDMSProvider writes the dms_provider field on dealer_web_presence.
	// Identified by domain (unique key).
	SetDMSProvider(ctx context.Context, domain, provider string) error

	// ListWebPresencesByDMSProvider returns all web presences with the given
	// dms_provider value. Used by E.2 directory mining and E.3 IP clustering.
	ListWebPresencesByDMSProvider(ctx context.Context, provider string) ([]*DealerWebPresence, error)

	// ListHostIPClusters returns groups where at least minDealers dealers share
	// the same CENSYS_HOST_ID or SHODAN_HOST_ID. Used by E.3 DMS clustering.
	ListHostIPClusters(ctx context.Context, minDealers int) ([]*HostIPCluster, error)
}
