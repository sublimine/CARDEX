// Package storage implements the pipeline.Storage interface using the shared
// SQLite knowledge graph database (same file used by the discovery service).
//
// The vehicle_record table and its indexes are defined in discovery's schema.sql.
// This package performs no schema migrations — it relies on the discovery
// service having already applied all migrations.
package storage

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
	_ "modernc.org/sqlite" // pure-Go SQLite driver

	"cardex.eu/extraction/internal/pipeline"
)

const schema = `
CREATE TABLE IF NOT EXISTS extraction_state (
  dealer_id          TEXT PRIMARY KEY,
  last_strategy      TEXT NOT NULL,
  last_extracted_at  TEXT NOT NULL,
  next_extraction_at TEXT NOT NULL,
  vehicles_found     INTEGER NOT NULL DEFAULT 0
);`

// SQLiteStorage implements pipeline.Storage.
type SQLiteStorage struct {
	db *sql.DB
}

// New opens the shared SQLite database and creates the extraction_state table
// if it does not exist. It does NOT apply discovery migrations.
func New(dbPath string) (*SQLiteStorage, error) {
	db, err := sql.Open("sqlite", dbPath+"?_journal_mode=WAL&_busy_timeout=10000")
	if err != nil {
		return nil, fmt.Errorf("storage.New: open %q: %w", dbPath, err)
	}
	db.SetMaxOpenConns(1)

	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("storage.New: create extraction_state: %w", err)
	}
	return &SQLiteStorage{db: db}, nil
}

// Close releases the database connection.
func (s *SQLiteStorage) Close() error {
	return s.db.Close()
}

// DealerExists returns true if the dealer_id is present in dealer_entity.
func (s *SQLiteStorage) DealerExists(ctx context.Context, dealerID string) (bool, error) {
	var count int
	err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM dealer_entity WHERE dealer_id = ?`, dealerID,
	).Scan(&count)
	if err != nil {
		return false, fmt.Errorf("storage.DealerExists: %w", err)
	}
	return count > 0, nil
}

// PersistVehicles upserts VehicleRaw records into vehicle_record.
// Vehicles whose dealer_id does not exist in dealer_entity are rejected.
// Returns the count of newly inserted rows.
func (s *SQLiteStorage) PersistVehicles(ctx context.Context, dealerID string, vehicles []*pipeline.VehicleRaw) (int, error) {
	exists, err := s.DealerExists(ctx, dealerID)
	if err != nil {
		return 0, err
	}
	if !exists {
		return 0, fmt.Errorf("storage.PersistVehicles: dealer %q not found in dealer_entity", dealerID)
	}

	const q = `
INSERT INTO vehicle_record (
  vehicle_id, vin, dealer_id,
  make_canonical, model_canonical, year,
  mileage_km, fuel_type, transmission, power_kw,
  body_type, color,
  price_net_eur, price_gross_eur, currency_original, vat_mode,
  source_url, source_listing_id, image_url,
  indexed_at, last_confirmed_at, ttl_expires_at,
  status, fingerprint_sha256, source_platform
) VALUES (?,?,?, ?,?,?, ?,?,?,?, ?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?,?)
ON CONFLICT(vin, dealer_id) WHERE vin IS NOT NULL DO UPDATE SET
  make_canonical      = excluded.make_canonical,
  model_canonical     = excluded.model_canonical,
  year                = excluded.year,
  mileage_km          = excluded.mileage_km,
  fuel_type           = excluded.fuel_type,
  transmission        = excluded.transmission,
  power_kw            = excluded.power_kw,
  body_type           = excluded.body_type,
  color               = excluded.color,
  price_net_eur       = excluded.price_net_eur,
  price_gross_eur     = excluded.price_gross_eur,
  currency_original   = excluded.currency_original,
  image_url           = excluded.image_url,
  last_confirmed_at   = excluded.last_confirmed_at,
  ttl_expires_at      = excluded.ttl_expires_at,
  fingerprint_sha256  = excluded.fingerprint_sha256`

	now := time.Now()
	ttl := now.Add(72 * time.Hour)

	inserted := 0
	for _, v := range vehicles {
		vehicleID := ulid.Make().String()
		fp := fingerprintVehicle(v)

		var (
			vin, make_, model_                   *string
			year, mileage, powerKW, doors, seats *int
			fuel, trans, body, color             *string
			priceNet, priceGross                 *float64
			currency, vatMode                    *string
			imageURL                             *string
		)

		vin = v.VIN
		make_ = v.Make
		model_ = v.Model
		year = v.Year
		mileage = v.Mileage
		powerKW = v.PowerKW
		fuel = v.FuelType
		trans = v.Transmission
		body = v.BodyType
		color = v.Color
		doors = v.Doors
		seats = v.Seats
		priceNet = v.PriceNet
		priceGross = v.PriceGross
		currency = v.Currency
		vatMode = v.VATMode
		_ = doors
		_ = seats

		if len(v.ImageURLs) > 0 {
			imageURL = &v.ImageURLs[0]
		}

		res, err := s.db.ExecContext(ctx, q,
			vehicleID, vin, dealerID,
			make_, model_, year,
			mileage, fuel, trans, powerKW,
			body, color,
			priceNet, priceGross, currency, vatMode,
			v.SourceURL, v.SourceListingID, imageURL,
			now.Format(time.RFC3339), now.Format(time.RFC3339), ttl.Format(time.RFC3339),
			"PENDING_REVIEW", fp, "extraction",
		)
		if err != nil {
			continue // log-and-continue on individual row errors
		}
		n, _ := res.RowsAffected()
		if n > 0 {
			inserted++
		}
	}
	return inserted, nil
}

// ListPendingDealers returns up to limit dealers whose next_extraction_at is in
// the past (or have never been extracted), ordered by next_extraction_at ASC.
func (s *SQLiteStorage) ListPendingDealers(ctx context.Context, limit int) ([]pipeline.Dealer, error) {
	const q = `
SELECT
  de.dealer_id, de.country_code,
  COALESCE(wp.domain, ''),
  COALESCE(wp.url_root, ''),
  COALESCE(wp.platform_type, 'UNKNOWN'),
  COALESCE(wp.dms_provider, ''),
  COALESCE(wp.cms_fingerprint_json, ''),
  COALESCE(wp.extraction_hints_json, '')
FROM dealer_entity de
LEFT JOIN dealer_web_presence wp ON wp.dealer_id = de.dealer_id
LEFT JOIN extraction_state es   ON es.dealer_id  = de.dealer_id
WHERE (es.next_extraction_at IS NULL OR es.next_extraction_at < ?)
  AND wp.domain IS NOT NULL
ORDER BY COALESCE(es.next_extraction_at, '1970-01-01') ASC
LIMIT ?`

	rows, err := s.db.QueryContext(ctx, q, time.Now().Format(time.RFC3339), limit)
	if err != nil {
		return nil, fmt.Errorf("storage.ListPendingDealers: %w", err)
	}
	defer rows.Close()

	var dealers []pipeline.Dealer
	for rows.Next() {
		var d pipeline.Dealer
		var cmsJSON, hintsJSON string
		if err := rows.Scan(
			&d.ID, &d.CountryCode,
			&d.Domain, &d.URLRoot, &d.PlatformType, &d.DMSProvider,
			&cmsJSON, &hintsJSON,
		); err != nil {
			return nil, fmt.Errorf("storage.ListPendingDealers scan: %w", err)
		}
		d.ExtractionHints = extractHints(cmsJSON, hintsJSON)
		d.CMSDetected = extractCMS(cmsJSON)
		dealers = append(dealers, d)
	}
	return dealers, rows.Err()
}

// MarkExtractionDone records a completed extraction run for a dealer.
func (s *SQLiteStorage) MarkExtractionDone(ctx context.Context, dealerID, strategyID string) error {
	now := time.Now()
	// Recheck intervals: E01/E02 → 24 h; E03/E04 → 48 h; others → 72 h.
	var recheckH int
	switch strategyID {
	case "E01", "E02":
		recheckH = 24
	case "E03", "E04":
		recheckH = 48
	default:
		recheckH = 72
	}
	next := now.Add(time.Duration(recheckH) * time.Hour)

	_, err := s.db.ExecContext(ctx, `
INSERT INTO extraction_state (dealer_id, last_strategy, last_extracted_at, next_extraction_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(dealer_id) DO UPDATE SET
  last_strategy      = excluded.last_strategy,
  last_extracted_at  = excluded.last_extracted_at,
  next_extraction_at = excluded.next_extraction_at`,
		dealerID, strategyID, now.Format(time.RFC3339), next.Format(time.RFC3339),
	)
	if err != nil {
		return fmt.Errorf("storage.MarkExtractionDone: %w", err)
	}
	return nil
}

// fingerprintVehicle returns a SHA-256 hex digest of the vehicle's key fields.
// Used to detect changes without overwriting unchanged records.
func fingerprintVehicle(v *pipeline.VehicleRaw) string {
	b, _ := json.Marshal(struct {
		VIN        *string
		Make       *string
		Model      *string
		Year       *int
		Mileage    *int
		PriceNet   *float64
		PriceGross *float64
		SourceURL  string
	}{
		VIN: v.VIN, Make: v.Make, Model: v.Model,
		Year: v.Year, Mileage: v.Mileage,
		PriceNet: v.PriceNet, PriceGross: v.PriceGross,
		SourceURL: v.SourceURL,
	})
	sum := sha256.Sum256(b)
	return fmt.Sprintf("%x", sum[:8]) // 16-char hex prefix is enough for dedup
}

// extractCMS parses the cms_fingerprint_json blob from Familia D.
func extractCMS(cmsJSON string) string {
	if cmsJSON == "" {
		return ""
	}
	var obj struct {
		CMS string `json:"cms"`
	}
	if err := json.Unmarshal([]byte(cmsJSON), &obj); err != nil {
		return ""
	}
	return strings.ToLower(obj.CMS)
}

// extractHints parses hints from both cms_fingerprint_json and extraction_hints_json.
func extractHints(cmsJSON, hintsJSON string) []string {
	var hints []string

	if cmsJSON != "" {
		var obj struct {
			CMS     string   `json:"cms"`
			Plugins []string `json:"plugins"`
		}
		if err := json.Unmarshal([]byte(cmsJSON), &obj); err == nil {
			if obj.CMS != "" {
				hints = append(hints, "cms:"+strings.ToLower(obj.CMS))
			}
			hints = append(hints, obj.Plugins...)
		}
	}

	if hintsJSON != "" {
		var obj struct {
			SchemaOrg bool     `json:"schema_org_detected"`
			Plugins   []string `json:"plugins"`
		}
		if err := json.Unmarshal([]byte(hintsJSON), &obj); err == nil {
			if obj.SchemaOrg {
				hints = append(hints, "schema_org_detected")
			}
			hints = append(hints, obj.Plugins...)
		}
	}

	return hints
}
