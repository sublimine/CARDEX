// Package storage persists and retrieves DealerTrustProfiles from SQLite.
// It also reads dealer signals from the shared discovery/extraction KG tables.
package storage

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/trust/internal/model"
	"cardex.eu/trust/internal/profiler"
)

const createTable = `
CREATE TABLE IF NOT EXISTS dealer_trust_profiles (
  dealer_id           TEXT PRIMARY KEY,
  dealer_name         TEXT NOT NULL DEFAULT '',
  country             TEXT NOT NULL DEFAULT '',
  vat_id              TEXT NOT NULL DEFAULT '',
  vies_status         TEXT NOT NULL DEFAULT 'unchecked',
  registry_status     TEXT NOT NULL DEFAULT 'unchecked',
  registry_age_years  INTEGER NOT NULL DEFAULT 0,
  v15_score           REAL NOT NULL DEFAULT 0.0,
  listing_volume      INTEGER NOT NULL DEFAULT 0,
  avg_composite_score REAL NOT NULL DEFAULT 0.0,
  index_tenure_days   INTEGER NOT NULL DEFAULT 0,
  anomaly_count       INTEGER NOT NULL DEFAULT 0,
  trust_score         REAL NOT NULL DEFAULT 0.0,
  trust_tier          TEXT NOT NULL DEFAULT 'unverified',
  badge_url           TEXT NOT NULL DEFAULT '',
  issued_at           TEXT NOT NULL,
  expires_at          TEXT NOT NULL,
  profile_hash        TEXT NOT NULL DEFAULT '',
  eidas_wallet_did    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trust_tier    ON dealer_trust_profiles(trust_tier);
CREATE INDEX IF NOT EXISTS idx_trust_country ON dealer_trust_profiles(country);
CREATE INDEX IF NOT EXISTS idx_trust_hash    ON dealer_trust_profiles(profile_hash);
`

// Store wraps the SQLite database and exposes trust-profile persistence operations.
type Store struct {
	db *sql.DB
}

// New opens (or creates) the SQLite database at path and runs schema migrations.
func New(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("storage: open %q: %w", path, err)
	}
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(createTable); err != nil {
		db.Close()
		return nil, fmt.Errorf("storage: migrate: %w", err)
	}
	return &Store{db: db}, nil
}

// Close releases the database connection.
func (s *Store) Close() error { return s.db.Close() }

// Upsert inserts or replaces a trust profile.
func (s *Store) Upsert(ctx context.Context, p *model.DealerTrustProfile) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO dealer_trust_profiles (
			dealer_id, dealer_name, country, vat_id,
			vies_status, registry_status, registry_age_years,
			v15_score, listing_volume, avg_composite_score,
			index_tenure_days, anomaly_count,
			trust_score, trust_tier, badge_url,
			issued_at, expires_at, profile_hash, eidas_wallet_did
		) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
		ON CONFLICT(dealer_id) DO UPDATE SET
			dealer_name=excluded.dealer_name, country=excluded.country,
			vat_id=excluded.vat_id, vies_status=excluded.vies_status,
			registry_status=excluded.registry_status, registry_age_years=excluded.registry_age_years,
			v15_score=excluded.v15_score, listing_volume=excluded.listing_volume,
			avg_composite_score=excluded.avg_composite_score, index_tenure_days=excluded.index_tenure_days,
			anomaly_count=excluded.anomaly_count, trust_score=excluded.trust_score,
			trust_tier=excluded.trust_tier, badge_url=excluded.badge_url,
			issued_at=excluded.issued_at, expires_at=excluded.expires_at,
			profile_hash=excluded.profile_hash, eidas_wallet_did=excluded.eidas_wallet_did`,
		p.DealerID, p.DealerName, p.Country, p.VATID,
		p.VIESStatus, p.RegistryStatus, p.RegistryAge,
		p.V15Score, p.ListingVolume, p.AvgCompositeScore,
		p.IndexTenureDays, p.AnomalyCount,
		p.TrustScore, p.TrustTier, p.BadgeURL,
		p.IssuedAt.UTC().Format(time.RFC3339),
		p.ExpiresAt.UTC().Format(time.RFC3339),
		p.ProfileHash, p.EIDASWalletDID,
	)
	return err
}

// Get returns the trust profile for the given dealer ID.
func (s *Store) Get(ctx context.Context, dealerID string) (*model.DealerTrustProfile, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT dealer_id, dealer_name, country, vat_id,
		       vies_status, registry_status, registry_age_years,
		       v15_score, listing_volume, avg_composite_score,
		       index_tenure_days, anomaly_count,
		       trust_score, trust_tier, badge_url,
		       issued_at, expires_at, profile_hash, eidas_wallet_did
		FROM dealer_trust_profiles WHERE dealer_id = ?`, dealerID)
	return scanProfile(row)
}

// GetByHash returns the trust profile matching the given SHA-256 profile hash.
func (s *Store) GetByHash(ctx context.Context, hash string) (*model.DealerTrustProfile, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT dealer_id, dealer_name, country, vat_id,
		       vies_status, registry_status, registry_age_years,
		       v15_score, listing_volume, avg_composite_score,
		       index_tenure_days, anomaly_count,
		       trust_score, trust_tier, badge_url,
		       issued_at, expires_at, profile_hash, eidas_wallet_did
		FROM dealer_trust_profiles WHERE profile_hash = ?`, hash)
	return scanProfile(row)
}

// ListFilter holds optional filters for List.
type ListFilter struct {
	Tier    string
	Country string
	Limit   int
}

// List returns trust profiles ordered by trust_score descending.
func (s *Store) List(ctx context.Context, f ListFilter) ([]*model.DealerTrustProfile, error) {
	limit := f.Limit
	if limit <= 0 {
		limit = 50
	}
	q := `
		SELECT dealer_id, dealer_name, country, vat_id,
		       vies_status, registry_status, registry_age_years,
		       v15_score, listing_volume, avg_composite_score,
		       index_tenure_days, anomaly_count,
		       trust_score, trust_tier, badge_url,
		       issued_at, expires_at, profile_hash, eidas_wallet_did
		FROM dealer_trust_profiles WHERE 1=1`
	var args []any
	if f.Tier != "" {
		q += " AND trust_tier = ?"
		args = append(args, f.Tier)
	}
	if f.Country != "" {
		q += " AND UPPER(country) = UPPER(?)"
		args = append(args, f.Country)
	}
	q += " ORDER BY trust_score DESC LIMIT ?"
	args = append(args, limit)

	rows, err := s.db.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var profiles []*model.DealerTrustProfile
	for rows.Next() {
		p, err := scanProfileRow(rows)
		if err != nil {
			return nil, err
		}
		profiles = append(profiles, p)
	}
	return profiles, rows.Err()
}

// DealerSignals holds the raw signals fetched from the shared KG for one dealer.
type DealerSignals struct {
	DealerID          string
	DealerName        string
	Country           string
	VATID             string
	FoundedYear       int
	Status            string
	FirstDiscoveredAt time.Time
	ListingVolume     int
	AvgCompositeScore float64
	AnomalyCount      int
	V15Score          float64
}

// FetchSignals queries dealer_entity and vehicle_record in the KG database
// and returns the raw signals needed by the profiler.
// db should be the shared discovery.db opened by the caller.
func FetchSignals(ctx context.Context, db *sql.DB, dealerID string) (*DealerSignals, error) {
	row := db.QueryRowContext(ctx, `
		SELECT
			de.dealer_id,
			COALESCE(de.canonical_name, ''),
			COALESCE(de.country_code, ''),
			COALESCE(de.primary_vat, ''),
			COALESCE(de.founded_year, 0),
			COALESCE(de.status, 'UNVERIFIED'),
			COALESCE(de.first_discovered_at, '1970-01-01T00:00:00Z'),
			COUNT(vr.vehicle_id) AS listing_volume,
			AVG(COALESCE(vr.confidence_score, 0)) * 100.0 AS avg_composite_score,
			SUM(CASE WHEN vr.manual_review_required = 1 AND vr.manual_review_verdict = 'REJECTED' THEN 1 ELSE 0 END) AS anomaly_count
		FROM dealer_entity de
		LEFT JOIN vehicle_record vr ON vr.dealer_id = de.dealer_id
		WHERE de.dealer_id = ?
		GROUP BY de.dealer_id`, dealerID)

	var sig DealerSignals
	var firstDiscoveredStr string
	var foundedYear sql.NullInt64
	err := row.Scan(
		&sig.DealerID, &sig.DealerName, &sig.Country, &sig.VATID,
		&foundedYear, &sig.Status, &firstDiscoveredStr,
		&sig.ListingVolume, &sig.AvgCompositeScore, &sig.AnomalyCount,
	)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("dealer %q not found", dealerID)
	}
	if err != nil {
		return nil, err
	}
	sig.FoundedYear = int(foundedYear.Int64)
	sig.FirstDiscoveredAt, _ = time.Parse(time.RFC3339, firstDiscoveredStr)

	// V15 trust score from quality pipeline validation results
	db.QueryRowContext(ctx, `
		SELECT AVG(COALESCE(confidence, 0)) * 100
		FROM validation_result
		WHERE validator_id = 'V15'
		  AND vehicle_id IN (SELECT vehicle_id FROM vehicle_record WHERE dealer_id = ?)`,
		dealerID).Scan(&sig.V15Score)

	return &sig, nil
}

// SignalsToInput converts fetched KG signals into a profiler.Input.
func SignalsToInput(sig *DealerSignals, badgeBaseURL string, now time.Time) profiler.Input {
	if now.IsZero() {
		now = time.Now().UTC()
	}

	viesStatus := "unchecked"
	if sig.VATID != "" && sig.Status == "ACTIVE" {
		viesStatus = "valid"
	}

	registryStatus := "unchecked"
	registryAge := 0
	if sig.FoundedYear > 0 {
		registryStatus = "registered"
		registryAge = now.Year() - sig.FoundedYear
		if registryAge < 0 {
			registryAge = 0
		}
	}

	tenureDays := int(now.Sub(sig.FirstDiscoveredAt).Hours() / 24)
	if tenureDays < 0 {
		tenureDays = 0
	}

	return profiler.Input{
		DealerID:          sig.DealerID,
		DealerName:        sig.DealerName,
		Country:           sig.Country,
		VATID:             sig.VATID,
		VIESStatus:        viesStatus,
		RegistryStatus:    registryStatus,
		RegistryAge:       registryAge,
		V15Score:          sig.V15Score,
		ListingVolume:     sig.ListingVolume,
		AvgCompositeScore: sig.AvgCompositeScore,
		IndexTenureDays:   tenureDays,
		AnomalyCount:      sig.AnomalyCount,
		BadgeBaseURL:      badgeBaseURL,
		Now:               now,
	}
}

// ListEligibleDealers returns dealer IDs from the KG with >= minListings active listings.
func ListEligibleDealers(ctx context.Context, db *sql.DB, minListings int) ([]string, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT de.dealer_id
		FROM dealer_entity de
		WHERE (
			SELECT COUNT(*) FROM vehicle_record vr
			WHERE vr.dealer_id = de.dealer_id
		) >= ?
		ORDER BY de.dealer_id`, minListings)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// ── scan helpers ──────────────────────────────────────────────────────────────

func scanProfile(row *sql.Row) (*model.DealerTrustProfile, error) {
	type scanner interface {
		Scan(dest ...any) error
	}
	return scanProfileScanner(row)
}

func scanProfileScanner(row *sql.Row) (*model.DealerTrustProfile, error) {
	var p model.DealerTrustProfile
	var issuedStr, expiresStr string
	err := row.Scan(
		&p.DealerID, &p.DealerName, &p.Country, &p.VATID,
		&p.VIESStatus, &p.RegistryStatus, &p.RegistryAge,
		&p.V15Score, &p.ListingVolume, &p.AvgCompositeScore,
		&p.IndexTenureDays, &p.AnomalyCount,
		&p.TrustScore, &p.TrustTier, &p.BadgeURL,
		&issuedStr, &expiresStr, &p.ProfileHash, &p.EIDASWalletDID,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	p.IssuedAt, _ = time.Parse(time.RFC3339, issuedStr)
	p.ExpiresAt, _ = time.Parse(time.RFC3339, expiresStr)
	return &p, nil
}

func scanProfileRow(rows *sql.Rows) (*model.DealerTrustProfile, error) {
	var p model.DealerTrustProfile
	var issuedStr, expiresStr string
	err := rows.Scan(
		&p.DealerID, &p.DealerName, &p.Country, &p.VATID,
		&p.VIESStatus, &p.RegistryStatus, &p.RegistryAge,
		&p.V15Score, &p.ListingVolume, &p.AvgCompositeScore,
		&p.IndexTenureDays, &p.AnomalyCount,
		&p.TrustScore, &p.TrustTier, &p.BadgeURL,
		&issuedStr, &expiresStr, &p.ProfileHash, &p.EIDASWalletDID,
	)
	if err != nil {
		return nil, err
	}
	p.IssuedAt, _ = time.Parse(time.RFC3339, issuedStr)
	p.ExpiresAt, _ = time.Parse(time.RFC3339, expiresStr)
	return &p, nil
}
