// Package storage implements the quality pipeline's persistence layer.
//
// Validation results are written to the shared SQLite knowledge graph used
// by the discovery and extraction services. The schema is lazily migrated on
// first connection.
package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/quality/internal/pipeline"
)

const schema = `
CREATE TABLE IF NOT EXISTS validation_result (
    id             INTEGER  PRIMARY KEY AUTOINCREMENT,
    validator_id   TEXT     NOT NULL,
    vehicle_id     TEXT     NOT NULL,
    pass           BOOLEAN  NOT NULL,
    severity       TEXT     NOT NULL,
    issue          TEXT,
    confidence     REAL,
    suggested_json TEXT,
    evidence_json  TEXT,
    validated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_validation_vehicle   ON validation_result(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_validation_validator ON validation_result(validator_id);
CREATE INDEX IF NOT EXISTS idx_validation_pass      ON validation_result(pass);
`

// SQLiteStorage implements pipeline.Storage backed by a SQLite database.
type SQLiteStorage struct {
	db *sql.DB
}

// New opens (or creates) the SQLite database at path and runs schema migration.
func New(path string) (*SQLiteStorage, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("storage: open %s: %w", path, err)
	}
	db.SetMaxOpenConns(1) // SQLite is single-writer
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("storage: migrate schema: %w", err)
	}
	return &SQLiteStorage{db: db}, nil
}

// Close releases the database connection.
func (s *SQLiteStorage) Close() error { return s.db.Close() }

// PersistValidation inserts one validation result row.
func (s *SQLiteStorage) PersistValidation(ctx context.Context, r *pipeline.ValidationResult) error {
	suggested, err := json.Marshal(r.Suggested)
	if err != nil {
		return fmt.Errorf("marshal suggested: %w", err)
	}
	evidence, err := json.Marshal(r.Evidence)
	if err != nil {
		return fmt.Errorf("marshal evidence: %w", err)
	}

	_, err = s.db.ExecContext(ctx,
		`INSERT INTO validation_result
		 (validator_id, vehicle_id, pass, severity, issue, confidence, suggested_json, evidence_json, validated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		r.ValidatorID,
		r.VehicleID,
		r.Pass,
		string(r.Severity),
		r.Issue,
		r.Confidence,
		string(suggested),
		string(evidence),
		time.Now().UTC().Format(time.RFC3339),
	)
	return err
}

// GetVehicleByID is a stub — full vehicle hydration from KG is implemented in Phase 5.
// Returns a minimal Vehicle with just the ID populated so the pipeline can operate
// without a fully integrated KG reader.
func (s *SQLiteStorage) GetVehicleByID(_ context.Context, id string) (*pipeline.Vehicle, error) {
	return &pipeline.Vehicle{InternalID: id}, nil
}

// ListPendingVehicles returns up to limit vehicles that have not yet been validated.
// It queries the vehicle_raw table (written by the extraction service) and returns
// vehicles that have no validation_result row yet.
//
// Phase 5 note: when the KG schema stabilises, this will join against the full
// vehicle enrichment table. For Sprint 19 it returns an empty slice if the table
// does not exist yet, so the service starts cleanly against a fresh DB.
func (s *SQLiteStorage) ListPendingVehicles(ctx context.Context, limit int) ([]*pipeline.Vehicle, error) {
	// Check if the vehicle_raw table exists before querying.
	var exists int
	err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vehicle_raw'`,
	).Scan(&exists)
	if err != nil || exists == 0 {
		return nil, nil
	}

	rows, err := s.db.QueryContext(ctx, `
		SELECT vr.id, vr.vin, vr.make, vr.model, vr.year, vr.mileage,
		       vr.price_eur, vr.title, vr.source_url, vr.dealer_id, vr.country_code
		FROM vehicle_raw vr
		WHERE NOT EXISTS (
			SELECT 1 FROM validation_result vres WHERE vres.vehicle_id = vr.id
		)
		LIMIT ?
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("list pending vehicles: %w", err)
	}
	defer rows.Close()

	var vehicles []*pipeline.Vehicle
	for rows.Next() {
		v := &pipeline.Vehicle{}
		var (
			vin, make_, model, title, sourceURL, dealerID, country sql.NullString
			year, mileage, priceEUR                                 sql.NullInt64
		)
		if err := rows.Scan(
			&v.InternalID, &vin, &make_, &model, &year, &mileage,
			&priceEUR, &title, &sourceURL, &dealerID, &country,
		); err != nil {
			return nil, fmt.Errorf("scan vehicle row: %w", err)
		}
		v.VIN = vin.String
		v.Make = make_.String
		v.Model = model.String
		v.Year = int(year.Int64)
		v.Mileage = int(mileage.Int64)
		v.PriceEUR = int(priceEUR.Int64)
		v.Title = title.String
		v.SourceURL = sourceURL.String
		v.DealerID = dealerID.String
		v.SourceCountry = country.String
		vehicles = append(vehicles, v)
	}
	return vehicles, rows.Err()
}

// GetVehiclesByVIN returns all vehicle records sharing the given VIN, used by V12 dedup.
// Returns nil (not an error) if the vehicle_raw table does not exist yet.
func (s *SQLiteStorage) GetVehiclesByVIN(ctx context.Context, vin string) ([]vehicleRef, error) {
	var exists int
	err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vehicle_raw'`,
	).Scan(&exists)
	if err != nil || exists == 0 {
		return nil, nil
	}

	rows, err := s.db.QueryContext(ctx,
		`SELECT id, vin, source_url, dealer_id FROM vehicle_raw WHERE vin = ?`, vin)
	if err != nil {
		return nil, fmt.Errorf("get vehicles by vin: %w", err)
	}
	defer rows.Close()

	var refs []vehicleRef
	for rows.Next() {
		var r vehicleRef
		var (
			sourceURL sql.NullString
			dealerID  sql.NullString
		)
		if err := rows.Scan(&r.InternalID, &r.VIN, &sourceURL, &dealerID); err != nil {
			return nil, fmt.Errorf("scan vehicle ref: %w", err)
		}
		r.SourceURL = sourceURL.String
		r.DealerID = dealerID.String
		refs = append(refs, r)
	}
	return refs, rows.Err()
}

// vehicleRef is a minimal vehicle entry used for VIN cross-referencing.
type vehicleRef struct {
	InternalID string
	VIN        string
	SourceURL  string
	DealerID   string
}

// GetDealerByID returns the trust record for a dealer, used by V15.
// Returns nil (not an error) if the dealer_entity table does not exist yet.
func (s *SQLiteStorage) GetDealerByID(ctx context.Context, dealerID string) (*dealerRecord, error) {
	var exists int
	err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dealer_entity'`,
	).Scan(&exists)
	if err != nil || exists == 0 {
		return nil, nil
	}

	var d dealerRecord
	var name sql.NullString
	var score sql.NullFloat64
	var sources sql.NullInt64
	err = s.db.QueryRowContext(ctx,
		`SELECT id, name, confidence_score, data_sources FROM dealer_entity WHERE id = ?`, dealerID,
	).Scan(&d.ID, &name, &score, &sources)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("get dealer by id: %w", err)
	}
	d.Name = name.String
	d.ConfidenceScore = score.Float64
	d.DataSources = int(sources.Int64)
	return &d, nil
}

// dealerRecord holds trust data for a dealer entity.
type dealerRecord struct {
	ID              string
	Name            string
	ConfidenceScore float64
	DataSources     int
}
