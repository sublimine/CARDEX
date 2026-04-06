// Package entityres provides cross-source entity resolution for vehicles and
// dealers. Uses exact VIN matching and Fellegi-Sunter-inspired probabilistic
// matching for listings without VINs.
package entityres

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"log/slog"
	"math"

	"github.com/jackc/pgx/v5/pgxpool"
)

// MatchByVIN finds vehicles across portals that share the same VIN.
// Returns the number of match pairs inserted with confidence 1.0 (exact match).
// Only considers ACTIVE listings to avoid stale cross-matches.
func MatchByVIN(ctx context.Context, pg *pgxpool.Pool) (int, error) {
	log.Println("[entityres] MatchByVIN: start")

	// Self-join on VIN across different platforms. Use a CTE to pre-filter
	// vehicles with non-null VINs and ACTIVE status, then cross-match.
	q := `
		WITH vin_vehicles AS (
			SELECT DISTINCT ON (vin, source_platform)
				vehicle_ulid, vin, source_platform, source_country
			FROM vehicles
			WHERE vin IS NOT NULL
			  AND LENGTH(vin) = 17
			  AND listing_status = 'ACTIVE'
			ORDER BY vin, source_platform, last_updated_at DESC
		)
		INSERT INTO entity_matches
			(match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source,
			 confidence, match_method, match_fields)
		SELECT
			'VEHICLE',
			a.vehicle_ulid,
			a.source_platform,
			b.vehicle_ulid,
			b.source_platform,
			1.000,
			'VIN_EXACT',
			jsonb_build_object('vin', a.vin)
		FROM vin_vehicles a
		JOIN vin_vehicles b
			ON a.vin = b.vin
			AND a.source_platform < b.source_platform
			AND a.vehicle_ulid < b.vehicle_ulid
		ON CONFLICT (match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source)
		DO UPDATE SET
			confidence = EXCLUDED.confidence,
			match_fields = EXCLUDED.match_fields
		RETURNING id
	`

	rows, err := pg.Query(ctx, q)
	if err != nil {
		return 0, fmt.Errorf("entityres: MatchByVIN query: %w", err)
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			continue
		}
		count++
	}
	if err := rows.Err(); err != nil {
		return count, fmt.Errorf("entityres: MatchByVIN rows: %w", err)
	}

	log.Printf("[entityres] MatchByVIN: inserted/updated %d match pairs", count)
	return count, nil
}

// fingerprintCandidate holds the fields used for probabilistic matching.
type fingerprintCandidate struct {
	VehicleULID    string
	SourcePlatform string
	Make           string
	Model          string
	Year           int
	MileageKM      *int
	PriceEUR       *float64
	H3Res7         *string
	Color          *string
}

// MatchByFingerprint finds probable matches using fuzzy attribute matching
// when VIN is not available. Uses Fellegi-Sunter-inspired scoring:
//   - Same make+model+year: +2.0
//   - Mileage within 500km:  +1.5
//   - Price within 5%:        +1.0
//   - Same H3 res7 cell:     +1.5
//   - Same color:             +0.5
//
// Total >= 5.0 -> match (confidence = score/6.5)
// Returns the number of match pairs inserted.
func MatchByFingerprint(ctx context.Context, pg *pgxpool.Pool) (int, error) {
	log.Println("[entityres] MatchByFingerprint: start")

	// Phase 1: Load candidates without VINs grouped by make+model+year+country
	// to keep the comparison space tractable. We only compare within the same
	// (make, model, year, source_country) bucket across different platforms.
	q := `
		SELECT vehicle_ulid, source_platform, make, model, year,
		       mileage_km, net_landed_cost_eur, h3_index_res7, color
		FROM vehicles
		WHERE (vin IS NULL OR LENGTH(vin) < 17)
		  AND listing_status = 'ACTIVE'
		  AND make IS NOT NULL AND make != ''
		  AND model IS NOT NULL AND model != ''
		  AND year IS NOT NULL AND year > 1990
		ORDER BY make, model, year, source_country, source_platform
	`

	rows, err := pg.Query(ctx, q)
	if err != nil {
		return 0, fmt.Errorf("entityres: MatchByFingerprint query: %w", err)
	}
	defer rows.Close()

	// Group candidates by (make, model, year) bucket.
	type bucketKey struct {
		Make, Model string
		Year        int
	}
	buckets := make(map[bucketKey][]fingerprintCandidate)

	for rows.Next() {
		var c fingerprintCandidate
		if err := rows.Scan(
			&c.VehicleULID, &c.SourcePlatform, &c.Make, &c.Model, &c.Year,
			&c.MileageKM, &c.PriceEUR, &c.H3Res7, &c.Color,
		); err != nil {
			continue
		}
		key := bucketKey{c.Make, c.Model, c.Year}
		buckets[key] = append(buckets[key], c)
	}
	if err := rows.Err(); err != nil {
		return 0, fmt.Errorf("entityres: MatchByFingerprint rows: %w", err)
	}

	// Phase 2: Pairwise scoring within each bucket, cross-platform only.
	const (
		wMakeModelYear = 2.0
		wMileage       = 1.5
		wPrice         = 1.0
		wH3            = 1.5
		wColor         = 0.5
		maxScore       = 6.5
		threshold      = 5.0
	)

	const maxBucketSize = 500

	inserted := 0
	for _, candidates := range buckets {
		if len(candidates) > maxBucketSize {
			slog.Warn("[entityres] MatchByFingerprint: bucket too large, sampling",
				"bucket", fmt.Sprintf("%s/%s/%d", candidates[0].Make, candidates[0].Model, candidates[0].Year),
				"size", len(candidates))
			candidates = candidates[:maxBucketSize]
		}
		for i := 0; i < len(candidates); i++ {
			for j := i + 1; j < len(candidates); j++ {
				a, b := candidates[i], candidates[j]

				// Only match across different platforms
				if a.SourcePlatform == b.SourcePlatform {
					continue
				}

				// Base score: same make+model+year (guaranteed by bucket)
				score := wMakeModelYear
				matchedFields := map[string]interface{}{
					"make":  a.Make,
					"model": a.Model,
					"year":  a.Year,
				}

				// Mileage within 500km
				if a.MileageKM != nil && b.MileageKM != nil {
					diff := math.Abs(float64(*a.MileageKM - *b.MileageKM))
					if diff <= 500 {
						score += wMileage
						matchedFields["mileage_delta_km"] = int(diff)
					}
				}

				// Price within 5%
				if a.PriceEUR != nil && b.PriceEUR != nil && *a.PriceEUR > 0 && *b.PriceEUR > 0 {
					avg := (*a.PriceEUR + *b.PriceEUR) / 2
					diff := math.Abs(*a.PriceEUR - *b.PriceEUR)
					if diff/avg <= 0.05 {
						score += wPrice
						matchedFields["price_diff_pct"] = math.Round(diff/avg*10000) / 100
					}
				}

				// Same H3 res7 cell
				if a.H3Res7 != nil && b.H3Res7 != nil && *a.H3Res7 == *b.H3Res7 && *a.H3Res7 != "" {
					score += wH3
					matchedFields["h3_res7"] = *a.H3Res7
				}

				// Same color
				if a.Color != nil && b.Color != nil && *a.Color == *b.Color && *a.Color != "" {
					score += wColor
					matchedFields["color"] = *a.Color
				}

				// Negative signal: large mileage divergence discredits match
				if a.MileageKM != nil && b.MileageKM != nil {
					diff := math.Abs(float64(*a.MileageKM - *b.MileageKM))
					if diff > 5000 {
						score -= 1.0
						matchedFields["mileage_penalty"] = int(diff)
					}
				}

				if score < threshold {
					continue
				}

				confidence := score / maxScore
				if confidence > 1.0 {
					confidence = 1.0
				}

				fieldsJSON, _ := json.Marshal(matchedFields)

				// Deterministic ordering: lower ULID first
				aID, aSrc, bID, bSrc := a.VehicleULID, a.SourcePlatform, b.VehicleULID, b.SourcePlatform
				if aID > bID {
					aID, aSrc, bID, bSrc = bID, bSrc, aID, aSrc
				}

				_, err := pg.Exec(ctx, `
					INSERT INTO entity_matches
						(match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source,
						 confidence, match_method, match_fields)
					VALUES ('VEHICLE', $1, $2, $3, $4, $5, 'FINGERPRINT_FELLEGI_SUNTER', $6)
					ON CONFLICT (match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source)
					DO UPDATE SET
						confidence = EXCLUDED.confidence,
						match_method = EXCLUDED.match_method,
						match_fields = EXCLUDED.match_fields
				`, aID, aSrc, bID, bSrc, math.Round(confidence*1000)/1000, fieldsJSON)
				if err != nil {
					log.Printf("[entityres] MatchByFingerprint insert: %v", err)
					continue
				}
				inserted++
			}
		}
	}

	log.Printf("[entityres] MatchByFingerprint: inserted/updated %d match pairs", inserted)
	return inserted, nil
}
