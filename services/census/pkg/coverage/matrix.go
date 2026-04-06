package coverage

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// DefaultTurnoverRate is the conservative annual turnover rate for passenger vehicles.
// ~12% of the fleet changes hands per year (EU average from ACEA, KBA, BOVAG data).
// This is the prior; it gets calibrated per segment once we have enough historical data.
const DefaultTurnoverRate = 0.12

// DefaultAvgDOM is the average days-on-market for a listed vehicle.
// 45 days is the EU cross-border average from industry reports.
const DefaultAvgDOM = 45

// ComputeMatrix calculates the coverage matrix from fleet_census + active vehicles.
//
// For each (country, make, year, fuel_type) cell:
//   expected_for_sale = fleet_count × turnover_rate × avg_dom / 365
//   coverage = observed_count / expected_for_sale
//   economic_value = (expected_for_sale - observed_count) × median_price
//
// The economic_value represents the monetary value of the vehicles we're NOT seeing.
// This is what drives crawl priority: high economic_value = high priority.
func ComputeMatrix(ctx context.Context, pg *pgxpool.Pool) (int, error) {
	slog.Info("coverage: computing matrix")
	start := time.Now()

	// Step 1: Get fleet counts from census, cross-joined with observed active listings.
	// We use a CTE to compute everything in a single atomic query.
	query := `
		WITH fleet AS (
			-- Latest census data per (country, make, year, fuel_type)
			SELECT DISTINCT ON (country, make, year, fuel_type)
				country, make, year, fuel_type, vehicle_count
			FROM fleet_census
			ORDER BY country, make, year, fuel_type, as_of_date DESC
		),
		observed AS (
			-- Active listings grouped by (source_country, make, year, fuel_type)
			SELECT
				source_country AS country,
				make,
				year,
				fuel_type,
				COUNT(*) AS observed_count,
				PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gross_physical_cost_eur) AS median_price
			FROM vehicles
			WHERE listing_status = 'ACTIVE'
				AND make IS NOT NULL
				AND year IS NOT NULL
				AND gross_physical_cost_eur > 0
			GROUP BY source_country, make, year, fuel_type
		),
		avg_dom AS (
			-- Average days-on-market per segment (from sold vehicles)
			SELECT
				source_country AS country,
				make,
				year,
				fuel_type,
				COALESCE(AVG(days_on_market), $1) AS avg_dom
			FROM vehicles
			WHERE listing_status IN ('ACTIVE', 'SOLD')
				AND days_on_market > 0
				AND make IS NOT NULL
			GROUP BY source_country, make, year, fuel_type
		)
		INSERT INTO coverage_matrix (
			country, make, year, fuel_type,
			fleet_count, turnover_rate, expected_for_sale,
			observed_count, coverage, economic_value_eur, median_price_eur
		)
		SELECT
			f.country,
			f.make,
			f.year,
			f.fuel_type,
			f.vehicle_count AS fleet_count,
			$2::NUMERIC AS turnover_rate,
			GREATEST(1, ROUND(f.vehicle_count * $2 * COALESCE(d.avg_dom, $1) / 365.0))::INT AS expected_for_sale,
			COALESCE(o.observed_count, 0)::INT AS observed_count,
			LEAST(
				COALESCE(o.observed_count, 0)::NUMERIC /
				GREATEST(1, ROUND(f.vehicle_count * $2 * COALESCE(d.avg_dom, $1) / 365.0)),
				9.9999
			) AS coverage,
			GREATEST(0,
				(ROUND(f.vehicle_count * $2 * COALESCE(d.avg_dom, $1) / 365.0) - COALESCE(o.observed_count, 0))
				* COALESCE(o.median_price, 15000)
			) AS economic_value_eur,
			COALESCE(o.median_price, 0) AS median_price_eur
		FROM fleet f
		LEFT JOIN observed o ON o.country = f.country AND o.make = f.make AND o.year = f.year
			AND (o.fuel_type = f.fuel_type OR (o.fuel_type IS NULL AND f.fuel_type IS NULL))
		LEFT JOIN avg_dom d ON d.country = f.country AND d.make = f.make AND d.year = f.year
			AND (d.fuel_type = f.fuel_type OR (d.fuel_type IS NULL AND f.fuel_type IS NULL))
		WHERE f.vehicle_count > 100
	`

	tag, err := pg.Exec(ctx, query, DefaultAvgDOM, DefaultTurnoverRate)
	if err != nil {
		return 0, fmt.Errorf("coverage: compute failed: %w", err)
	}

	rowCount := int(tag.RowsAffected())
	slog.Info("coverage: matrix computed",
		"rows", rowCount,
		"duration_ms", time.Since(start).Milliseconds(),
	)
	return rowCount, nil
}

// PruneOldSnapshots removes coverage_matrix rows older than 30 days.
func PruneOldSnapshots(ctx context.Context, pg *pgxpool.Pool) error {
	_, err := pg.Exec(ctx, `DELETE FROM coverage_matrix WHERE computed_at < NOW() - INTERVAL '30 days'`)
	return err
}
