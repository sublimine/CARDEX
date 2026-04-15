package kg

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
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
   opening_hours_json, phone, source_families)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`

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
		loc.Phone,
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

// ── Family M — VAT validation ─────────────────────────────────────────────────

// FindDealersForVATValidation returns dealers with a non-null primary_vat whose
// validation is absent or older than staleDays days, restricted to the given
// country codes.
func (g *SQLiteGraph) FindDealersForVATValidation(
	ctx context.Context,
	countries []string,
	staleDays int,
) ([]*DealerVATCandidate, error) {
	if len(countries) == 0 {
		return nil, nil
	}

	placeholders := make([]string, len(countries))
	args := make([]interface{}, len(countries)+1)
	for i, c := range countries {
		placeholders[i] = "?"
		args[i] = c
	}
	args[len(countries)] = staleDays

	q := `
SELECT dealer_id, primary_vat, country_code, canonical_name, confidence_score
FROM dealer_entity
WHERE primary_vat IS NOT NULL
  AND country_code IN (` + strings.Join(placeholders, ",") + `)
  AND (
    vat_validated_at IS NULL
    OR vat_validated_at < datetime('now', '-' || ? || ' days')
  )
ORDER BY dealer_id`

	rows, err := g.db.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, fmt.Errorf("kg.FindDealersForVATValidation: %w", err)
	}
	defer rows.Close()

	var candidates []*DealerVATCandidate
	for rows.Next() {
		c := &DealerVATCandidate{}
		if err := rows.Scan(&c.DealerID, &c.PrimaryVAT, &c.CountryCode, &c.CanonicalName, &c.ConfidenceScore); err != nil {
			return nil, fmt.Errorf("kg.FindDealersForVATValidation scan: %w", err)
		}
		candidates = append(candidates, c)
	}
	return candidates, rows.Err()
}

// UpdateVATValidation writes the vat_validated_at and vat_valid_status columns.
func (g *SQLiteGraph) UpdateVATValidation(ctx context.Context, dealerID string, validatedAt time.Time, status string) error {
	const q = `
UPDATE dealer_entity
SET vat_validated_at = ?, vat_valid_status = ?
WHERE dealer_id = ?`
	_, err := g.db.ExecContext(ctx, q,
		validatedAt.UTC().Format("2006-01-02T15:04:05Z"), status, dealerID)
	if err != nil {
		return fmt.Errorf("kg.UpdateVATValidation %q: %w", dealerID, err)
	}
	return nil
}

// UpdateConfidenceScore overwrites confidence_score for the given dealer.
func (g *SQLiteGraph) UpdateConfidenceScore(ctx context.Context, dealerID string, score float64) error {
	const q = `UPDATE dealer_entity SET confidence_score = ? WHERE dealer_id = ?`
	_, err := g.db.ExecContext(ctx, q, score, dealerID)
	if err != nil {
		return fmt.Errorf("kg.UpdateConfidenceScore %q: %w", dealerID, err)
	}
	return nil
}

// ── Family K — processing state ───────────────────────────────────────────────

// GetProcessingState returns the stored value for key, or ("", nil) if absent.
func (g *SQLiteGraph) GetProcessingState(ctx context.Context, key string) (string, error) {
	const q = `SELECT value FROM processing_state WHERE key = ?`
	var value string
	err := g.db.QueryRowContext(ctx, q, key).Scan(&value)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("kg.GetProcessingState %q: %w", key, err)
	}
	return value, nil
}

// SetProcessingState upserts (key, value) with the current UTC timestamp.
func (g *SQLiteGraph) SetProcessingState(ctx context.Context, key, value string) error {
	const q = `
INSERT INTO processing_state(key, value, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`
	_, err := g.db.ExecContext(ctx, q, key, value,
		time.Now().UTC().Format("2006-01-02T15:04:05Z"))
	if err != nil {
		return fmt.Errorf("kg.SetProcessingState %q: %w", key, err)
	}
	return nil
}

// -- Family D -- CMS fingerprinting -------------------------------------------

// ListWebPresencesForCMSScan returns web presences for the given country where
// cms_scanned_at IS NULL or older than staleDays days.
func (g *SQLiteGraph) ListWebPresencesForCMSScan(
	ctx context.Context,
	country string,
	staleDays, limit int,
) ([]*DealerWebPresence, error) {
	const q = `
SELECT wp.web_id, wp.dealer_id, wp.domain, wp.url_root,
       wp.platform_type, wp.dms_provider, wp.extraction_strategy,
       wp.discovered_by_families, wp.metadata_json,
       wp.cms_fingerprint_json, wp.cms_scanned_at, wp.extraction_hints_json
FROM dealer_web_presence wp
JOIN dealer_entity de ON de.dealer_id = wp.dealer_id
WHERE de.country_code = ?
  AND (wp.cms_scanned_at IS NULL
       OR wp.cms_scanned_at < datetime('now', '-' || ? || ' days'))
ORDER BY wp.web_id
LIMIT ?`

	rows, err := g.db.QueryContext(ctx, q, country, staleDays, limit)
	if err != nil {
		return nil, fmt.Errorf("kg.ListWebPresencesForCMSScan: %w", err)
	}
	defer rows.Close()

	var out []*DealerWebPresence
	for rows.Next() {
		wp := &DealerWebPresence{}
		var scannedAt sql.NullString
		if err := rows.Scan(
			&wp.WebID, &wp.DealerID, &wp.Domain, &wp.URLRoot,
			&wp.PlatformType, &wp.DMSProvider, &wp.ExtractionStrategy,
			&wp.DiscoveredByFamilies, &wp.MetadataJSON,
			&wp.CMSFingerprintJSON, &scannedAt, &wp.ExtractionHintsJSON,
		); err != nil {
			return nil, fmt.Errorf("kg.ListWebPresencesForCMSScan scan: %w", err)
		}
		if scannedAt.Valid {
			t, _ := time.Parse("2006-01-02T15:04:05Z", scannedAt.String)
			wp.CMSScannedAt = &t
		}
		out = append(out, wp)
	}
	return out, rows.Err()
}

// UpsertWebTechnology stores CMS fingerprint and extraction hints for a domain.
// Sets cms_scanned_at to the current UTC timestamp.
func (g *SQLiteGraph) UpsertWebTechnology(
	ctx context.Context,
	domain, cmsFingerprintJSON, extractionHintsJSON string,
) error {
	const q = `
UPDATE dealer_web_presence
SET cms_fingerprint_json  = ?,
    cms_scanned_at        = ?,
    extraction_hints_json = ?
WHERE domain = ?`
	_, err := g.db.ExecContext(ctx, q,
		cmsFingerprintJSON,
		time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		extractionHintsJSON,
		domain,
	)
	if err != nil {
		return fmt.Errorf("kg.UpsertWebTechnology %q: %w", domain, err)
	}
	return nil
}

// -- Family L -- social profiles ----------------------------------------------

// UpsertSocialProfile inserts or updates a social profile record.
// Conflict key: (dealer_id, platform, external_id) when external_id is set,
// or (dealer_id, platform, profile_url) otherwise.
func (g *SQLiteGraph) UpsertSocialProfile(
	ctx context.Context,
	p *DealerSocialProfile,
) error {
	const q = `
INSERT INTO dealer_social_profile
  (profile_id, dealer_id, platform, profile_url, external_id,
   rating, review_count, last_activity_detected, metadata_json)
VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT(profile_id) DO UPDATE SET
  profile_url           = excluded.profile_url,
  rating                = excluded.rating,
  review_count          = excluded.review_count,
  last_activity_detected = excluded.last_activity_detected,
  metadata_json         = excluded.metadata_json`

	var lastActivity *string
	if p.LastActivityDetected != nil {
		s := p.LastActivityDetected.UTC().Format("2006-01-02T15:04:05Z")
		lastActivity = &s
	}
	_, err := g.db.ExecContext(ctx, q,
		p.ProfileID, p.DealerID, p.Platform, p.ProfileURL, p.ExternalID,
		p.Rating, p.ReviewCount, lastActivity, p.MetadataJSON,
	)
	if err != nil {
		return fmt.Errorf("kg.UpsertSocialProfile %q/%s: %w", p.DealerID, p.Platform, err)
	}
	return nil
}

// -- Family J -- sub-jurisdiction / regional enrichment -----------------------

// ListDealersByCountry returns a lightweight province-candidate projection for
// all dealers in the given country.
func (g *SQLiteGraph) ListDealersByCountry(
	ctx context.Context,
	country string,
) ([]*DealerProvinceCandidate, error) {
	const q = `
SELECT de.dealer_id, dl.postal_code, dl.city, de.country_code
FROM dealer_entity de
LEFT JOIN dealer_location dl ON dl.dealer_id = de.dealer_id AND dl.is_primary = 1
WHERE de.country_code = ?
ORDER BY de.dealer_id`

	rows, err := g.db.QueryContext(ctx, q, country)
	if err != nil {
		return nil, fmt.Errorf("kg.ListDealersByCountry: %w", err)
	}
	defer rows.Close()

	var out []*DealerProvinceCandidate
	for rows.Next() {
		c := &DealerProvinceCandidate{}
		if err := rows.Scan(&c.DealerID, &c.PostalCode, &c.City, &c.CountryCode); err != nil {
			return nil, fmt.Errorf("kg.ListDealersByCountry scan: %w", err)
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// UpdateDealerSubRegion sets the region column on the primary location row for
// the given dealer. region is a province/state/gewest name (e.g. "Noord-Holland").
func (g *SQLiteGraph) UpdateDealerSubRegion(ctx context.Context, dealerID, subRegion string) error {
	const q = `
UPDATE dealer_location SET region = ?
WHERE dealer_id = ? AND is_primary = 1`
	_, err := g.db.ExecContext(ctx, q, subRegion, dealerID)
	if err != nil {
		return fmt.Errorf("kg.UpdateDealerSubRegion %q: %w", dealerID, err)
	}
	return nil
}

// -- Family N -- infrastructure intelligence ----------------------------------

// ListWebPresencesForInfraScan returns all web presences for the given country
// up to limit rows, ordered by web_id (stable pagination).
func (g *SQLiteGraph) ListWebPresencesForInfraScan(
	ctx context.Context,
	country string,
	limit int,
) ([]*DealerWebPresence, error) {
	const q = `
SELECT wp.web_id, wp.dealer_id, wp.domain, wp.url_root,
       wp.platform_type, wp.dms_provider, wp.extraction_strategy,
       wp.discovered_by_families, wp.metadata_json,
       wp.cms_fingerprint_json, wp.cms_scanned_at, wp.extraction_hints_json
FROM dealer_web_presence wp
JOIN dealer_entity de ON de.dealer_id = wp.dealer_id
WHERE de.country_code = ?
ORDER BY wp.web_id
LIMIT ?`

	rows, err := g.db.QueryContext(ctx, q, country, limit)
	if err != nil {
		return nil, fmt.Errorf("kg.ListWebPresencesForInfraScan: %w", err)
	}
	defer rows.Close()

	var out []*DealerWebPresence
	for rows.Next() {
		wp := &DealerWebPresence{}
		var scannedAt sql.NullString
		if err := rows.Scan(
			&wp.WebID, &wp.DealerID, &wp.Domain, &wp.URLRoot,
			&wp.PlatformType, &wp.DMSProvider, &wp.ExtractionStrategy,
			&wp.DiscoveredByFamilies, &wp.MetadataJSON,
			&wp.CMSFingerprintJSON, &scannedAt, &wp.ExtractionHintsJSON,
		); err != nil {
			return nil, fmt.Errorf("kg.ListWebPresencesForInfraScan scan: %w", err)
		}
		if scannedAt.Valid {
			t, _ := time.Parse("2006-01-02T15:04:05Z", scannedAt.String)
			wp.CMSScannedAt = &t
		}
		out = append(out, wp)
	}
	return out, rows.Err()
}
