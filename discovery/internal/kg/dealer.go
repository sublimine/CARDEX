package kg

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

// SQLiteGraph is the production KnowledgeGraph backed by a modernc.org/sqlite
// database opened via db.Open(). All writes go through a single *sql.DB with
// MaxOpenConns=1 to avoid SQLITE_BUSY in WAL mode.
type SQLiteGraph struct {
	db *sql.DB
}

// NewSQLiteGraph wraps an open *sql.DB (already migrated) as a KnowledgeGraph.
func NewSQLiteGraph(db *sql.DB) *SQLiteGraph {
	return &SQLiteGraph{db: db}
}

// UpsertDealer inserts a new dealer or updates canonical_name, status,
// confidence_score and last_confirmed_at on conflict.
func (g *SQLiteGraph) UpsertDealer(ctx context.Context, e *DealerEntity) error {
	const q = `
INSERT INTO dealer_entity
  (dealer_id, canonical_name, normalized_name, country_code,
   primary_vat, legal_form, founded_year, status,
   operational_score, confidence_score,
   first_discovered_at, last_confirmed_at, metadata_json)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(dealer_id) DO UPDATE SET
  canonical_name    = excluded.canonical_name,
  normalized_name   = excluded.normalized_name,
  status            = excluded.status,
  confidence_score  = excluded.confidence_score,
  last_confirmed_at = excluded.last_confirmed_at`

	_, err := g.db.ExecContext(ctx, q,
		e.DealerID,
		e.CanonicalName,
		e.NormalizedName,
		e.CountryCode,
		e.PrimaryVAT,
		e.LegalForm,
		e.FoundedYear,
		e.Status,
		e.OperationalScore,
		e.ConfidenceScore,
		e.FirstDiscoveredAt.UTC().Format("2006-01-02T15:04:05Z"),
		e.LastConfirmedAt.UTC().Format("2006-01-02T15:04:05Z"),
		e.MetadataJSON,
	)
	if err != nil {
		return fmt.Errorf("kg.UpsertDealer %q: %w", e.DealerID, err)
	}
	return nil
}

// AddIdentifier inserts a new identifier. If the (type, value) unique constraint
// fires the row already exists and the operation is treated as a no-op.
func (g *SQLiteGraph) AddIdentifier(ctx context.Context, id *DealerIdentifier) error {
	const q = `
INSERT OR IGNORE INTO dealer_identifier
  (identifier_id, dealer_id, identifier_type, identifier_value,
   source_family, valid_status)
VALUES (?,?,?,?,?,?)`

	_, err := g.db.ExecContext(ctx, q,
		id.IdentifierID,
		id.DealerID,
		string(id.IdentifierType),
		id.IdentifierValue,
		id.SourceFamily,
		id.ValidStatus,
	)
	if err != nil {
		return fmt.Errorf("kg.AddIdentifier %s/%s: %w",
			id.IdentifierType, id.IdentifierValue, err)
	}
	return nil
}

// AddLocation inserts a dealer location. Uses INSERT OR IGNORE so that
// re-running the same discovery cycle is safe.
func (g *SQLiteGraph) AddLocation(ctx context.Context, loc *DealerLocation) error {
	const q = `
INSERT OR IGNORE INTO dealer_location
  (location_id, dealer_id, is_primary,
   address_line1, address_line2, postal_code, city, region,
   country_code, lat, lon, h3_index,
   opening_hours_json, source_families)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`

	_, err := g.db.ExecContext(ctx, q,
		loc.LocationID,
		loc.DealerID,
		loc.IsPrimary,
		loc.AddressLine1,
		loc.AddressLine2,
		loc.PostalCode,
		loc.City,
		loc.Region,
		loc.CountryCode,
		loc.Lat,
		loc.Lon,
		loc.H3Index,
		loc.OpeningHoursJSON,
		loc.SourceFamilies,
	)
	if err != nil {
		return fmt.Errorf("kg.AddLocation %q: %w", loc.LocationID, err)
	}
	return nil
}

// RecordDiscovery writes an audit entry. Uses INSERT OR IGNORE — duplicate
// (dealer, family, sub_technique, discovered_at) combinations are dropped
// silently.
func (g *SQLiteGraph) RecordDiscovery(ctx context.Context, rec *DiscoveryRecord) error {
	const q = `
INSERT OR IGNORE INTO discovery_record
  (record_id, dealer_id, family, sub_technique,
   source_url, source_record_id,
   confidence_contributed, discovered_at)
VALUES (?,?,?,?,?,?,?,?)`

	_, err := g.db.ExecContext(ctx, q,
		rec.RecordID,
		rec.DealerID,
		rec.Family,
		rec.SubTechnique,
		rec.SourceURL,
		rec.SourceRecordID,
		rec.ConfidenceContributed,
		rec.DiscoveredAt.UTC().Format("2006-01-02T15:04:05Z"),
	)
	if err != nil {
		return fmt.Errorf("kg.RecordDiscovery %q: %w", rec.RecordID, err)
	}
	return nil
}

// FindDealerByIdentifier returns the dealer_id for the given (type, value) pair.
// Returns ("", nil) when the identifier is not present in the graph.
func (g *SQLiteGraph) FindDealerByIdentifier(
	ctx context.Context,
	idType IdentifierType,
	idValue string,
) (string, error) {
	const q = `
SELECT dealer_id FROM dealer_identifier
WHERE identifier_type = ? AND identifier_value = ?
LIMIT 1`

	var dealerID string
	err := g.db.QueryRowContext(ctx, q, string(idType), idValue).Scan(&dealerID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("kg.FindDealerByIdentifier %s/%s: %w", idType, idValue, err)
	}
	return dealerID, nil
}
