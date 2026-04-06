// Source overlap matrix computation for capture-recapture population estimation.
// Scheduled daily at 05:00 UTC.
package main

import (
	"context"
	"log"
)

// computeSourceOverlap queries the vehicles table for VIN-based cross-platform
// overlap within each country and computes Lincoln-Petersen population estimates.
// Results are inserted into the source_overlap_matrix table.
//
// Lincoln-Petersen formula: N_hat = (n1 * n2) / m2
// Chapman estimator (bias-corrected): N_c = ((n1+1)(n2+1))/(m2+1) - 1
// Variance: Var(N) = ((n1+1)(n2+1)(n1-m2)(n2-m2)) / ((m2+1)^2 * (m2+2))
// 95% CI: N_c ± 1.96 * sqrt(Var(N))
//
//   - n1 = total vehicles on source A (with valid VIN)
//   - n2 = total vehicles on source B (with valid VIN)
//   - m2 = vehicles with VIN appearing on both A and B
//
// Capture rates:
//   - capture_rate_a = overlap / n1  (fraction of A's population also on B)
//   - capture_rate_b = overlap / n2  (fraction of B's population also on A)
//
// Add to scheduler main():
//
//	go dailyAt(ctx, 5, d.computeSourceOverlap)
func (d *Deps) computeSourceOverlap(ctx context.Context) {
	if !d.tryAdvisoryLock(ctx, lockComputeSourceOverlap) {
		log.Println("[scheduler] computeSourceOverlap: skipped (another instance running)")
		return
	}
	defer d.releaseAdvisoryLock(ctx, lockComputeSourceOverlap)
	log.Println("[job] computeSourceOverlap: start")

	// Single query: for each (country, platform_a, platform_b) pair, compute
	// overlap, exclusive counts, and Lincoln-Petersen N using window functions
	// and self-join on VIN.
	q := `
		WITH vin_listings AS (
			SELECT DISTINCT ON (vin, source_platform)
				vin, source_platform, source_country
			FROM vehicles
			WHERE vin IS NOT NULL
			  AND LENGTH(vin) = 17
			  AND listing_status = 'ACTIVE'
			  AND source_country IS NOT NULL
		),
		platform_counts AS (
			SELECT source_country, source_platform, COUNT(*) AS total
			FROM vin_listings
			GROUP BY source_country, source_platform
		),
		pairs AS (
			SELECT
				a.source_country  AS country,
				a.source_platform AS source_a,
				b.source_platform AS source_b,
				COUNT(*)          AS overlap_count
			FROM vin_listings a
			JOIN vin_listings b
				ON a.vin = b.vin
				AND a.source_country = b.source_country
				AND a.source_platform < b.source_platform
			GROUP BY a.source_country, a.source_platform, b.source_platform
		)
		INSERT INTO source_overlap_matrix
			(country, source_a, source_b,
			 overlap_count, only_a_count, only_b_count,
			 lincoln_petersen_n, chapman_n, chapman_var, ci_lower, ci_upper,
			 capture_rate_a, capture_rate_b)
		SELECT
			p.country,
			p.source_a,
			p.source_b,
			p.overlap_count,
			(ca.total - p.overlap_count)  AS only_a_count,
			(cb.total - p.overlap_count)  AS only_b_count,
			-- Lincoln-Petersen: N = (n1 * n2) / m2
			CASE WHEN p.overlap_count > 0
				THEN (ca.total::NUMERIC * cb.total::NUMERIC) / p.overlap_count
				ELSE NULL
			END AS lincoln_petersen_n,
			-- Chapman estimator (bias-corrected): N_c = ((n1+1)(n2+1))/(m2+1) - 1
			CASE WHEN p.overlap_count > 0 THEN
				((ca.total + 1.0) * (cb.total + 1.0)) / (p.overlap_count + 1.0) - 1.0
				ELSE NULL
			END AS chapman_n,
			-- Chapman variance: Var(N) = ((n1+1)(n2+1)(n1-m2)(n2-m2)) / ((m2+1)^2*(m2+2))
			CASE WHEN p.overlap_count > 1 THEN
				((ca.total+1.0)*(cb.total+1.0)*(ca.total-p.overlap_count)*(cb.total-p.overlap_count))
				/ ((p.overlap_count+1.0)*(p.overlap_count+1.0)*(p.overlap_count+2.0))
				ELSE NULL
			END AS chapman_var,
			-- 95% CI lower bound
			CASE WHEN p.overlap_count > 1 THEN
				((ca.total + 1.0) * (cb.total + 1.0)) / (p.overlap_count + 1.0) - 1.0
				- 1.96 * |/( ((ca.total+1.0)*(cb.total+1.0)*(ca.total-p.overlap_count)*(cb.total-p.overlap_count))
				           / ((p.overlap_count+1.0)*(p.overlap_count+1.0)*(p.overlap_count+2.0)) )
				ELSE NULL
			END AS ci_lower,
			-- 95% CI upper bound
			CASE WHEN p.overlap_count > 1 THEN
				((ca.total + 1.0) * (cb.total + 1.0)) / (p.overlap_count + 1.0) - 1.0
				+ 1.96 * |/( ((ca.total+1.0)*(cb.total+1.0)*(ca.total-p.overlap_count)*(cb.total-p.overlap_count))
				           / ((p.overlap_count+1.0)*(p.overlap_count+1.0)*(p.overlap_count+2.0)) )
				ELSE NULL
			END AS ci_upper,
			-- Capture rate A = overlap / n1
			CASE WHEN ca.total > 0
				THEN p.overlap_count::NUMERIC / ca.total
				ELSE 0
			END AS capture_rate_a,
			-- Capture rate B = overlap / n2
			CASE WHEN cb.total > 0
				THEN p.overlap_count::NUMERIC / cb.total
				ELSE 0
			END AS capture_rate_b
		FROM pairs p
		JOIN platform_counts ca
			ON ca.source_country = p.country AND ca.source_platform = p.source_a
		JOIN platform_counts cb
			ON cb.source_country = p.country AND cb.source_platform = p.source_b
		WHERE p.overlap_count >= 3
	`

	tag, err := d.pg.Exec(ctx, q)
	if err != nil {
		log.Printf("[job] computeSourceOverlap: %v", err)
		return
	}
	log.Printf("[job] computeSourceOverlap: inserted %d platform pair rows", tag.RowsAffected())
}
