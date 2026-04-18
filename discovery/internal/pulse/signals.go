package pulse

import (
	"context"
	"database/sql"
	"fmt"
	"math"
	"time"
)

// ComputeSignals runs all seven SQL signal queries against db for dealerID and
// returns a fully-populated DealerHealthScore (raw signals only; Score/Tier/
// RiskSignals/TrendDirection are set by the scorer).
func ComputeSignals(ctx context.Context, db *sql.DB, dealerID string, now time.Time) (*DealerHealthScore, error) {
	s := &DealerHealthScore{
		DealerID:   dealerID,
		ComputedAt: now,
	}

	// -- dealer meta ------------------------------------------------------------
	if err := db.QueryRowContext(ctx,
		`SELECT canonical_name, country_code
		   FROM dealer_entity WHERE dealer_id = ?`, dealerID,
	).Scan(&s.DealerName, &s.Country); err != nil {
		return nil, fmt.Errorf("pulse.signals: dealer meta: %w", err)
	}

	// -- active listing count ---------------------------------------------------
	if err := db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM vehicle_record
		  WHERE dealer_id = ? AND status = 'ACTIVE'`, dealerID,
	).Scan(&s.ActiveCount); err != nil {
		return nil, fmt.Errorf("pulse.signals: active count: %w", err)
	}

	nowStr := now.UTC().Format(time.RFC3339)

	// -- 1. Liquidation ratio ---------------------------------------------------
	// removed = TTL expired in [now-14d, now]; new = indexed in [now-14d, now].
	var removed, newCount int
	if err := db.QueryRowContext(ctx, `
		SELECT
		  COALESCE(SUM(CASE WHEN ttl_expires_at >= datetime(?, '-14 days')
		                     AND ttl_expires_at <= datetime(?) THEN 1 ELSE 0 END), 0),
		  COALESCE(SUM(CASE WHEN indexed_at >= datetime(?, '-14 days') THEN 1 ELSE 0 END), 0)
		FROM vehicle_record
		WHERE dealer_id = ? AND status NOT IN ('REJECTED','DUPLICATE')`,
		nowStr, nowStr, nowStr, dealerID,
	).Scan(&removed, &newCount); err != nil {
		return nil, fmt.Errorf("pulse.signals: liquidation: %w", err)
	}
	if newCount > 0 {
		s.LiquidationRatio = float64(removed) / float64(newCount)
	}

	// -- 2. Price trend (%/week) ------------------------------------------------
	var recentPrice, priorPrice sql.NullFloat64
	if err := db.QueryRowContext(ctx, `
		SELECT
		  AVG(CASE WHEN indexed_at >= datetime(?, '-7 days')  THEN price_gross_eur END),
		  AVG(CASE WHEN indexed_at >= datetime(?, '-14 days')
		            AND indexed_at <  datetime(?, '-7 days')   THEN price_gross_eur END)
		FROM vehicle_record
		WHERE dealer_id = ? AND status = 'ACTIVE' AND price_gross_eur > 0`,
		nowStr, nowStr, nowStr, dealerID,
	).Scan(&recentPrice, &priorPrice); err != nil {
		return nil, fmt.Errorf("pulse.signals: price trend: %w", err)
	}
	if recentPrice.Valid && priorPrice.Valid && priorPrice.Float64 > 0 {
		s.PriceTrend = ((recentPrice.Float64 - priorPrice.Float64) / priorPrice.Float64) * 100
	}

	// -- 3. Volume z-score (current week vs 90-day weekly baseline) --------------
	rows, err := db.QueryContext(ctx, `
		SELECT strftime('%W-%Y', indexed_at) as wk, COUNT(*) as cnt
		FROM vehicle_record
		WHERE dealer_id = ? AND status NOT IN ('REJECTED','DUPLICATE')
		  AND indexed_at >= datetime(?, '-90 days')
		GROUP BY wk
		ORDER BY wk`,
		dealerID, nowStr,
	)
	if err != nil {
		return nil, fmt.Errorf("pulse.signals: volume z-score: %w", err)
	}
	defer rows.Close()

	var weeklyCounts []float64
	for rows.Next() {
		var wk string
		var cnt float64
		if err := rows.Scan(&wk, &cnt); err != nil {
			return nil, fmt.Errorf("pulse.signals: volume z-score scan: %w", err)
		}
		weeklyCounts = append(weeklyCounts, cnt)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pulse.signals: volume z-score rows: %w", err)
	}
	s.VolumeZScore = computeZScore(weeklyCounts)

	// -- 4 & 5. Time on market (days) + delta ------------------------------------
	var avgToM sql.NullFloat64
	if err := db.QueryRowContext(ctx, `
		SELECT AVG(julianday(?) - julianday(indexed_at))
		FROM vehicle_record
		WHERE dealer_id = ? AND status = 'ACTIVE'`,
		nowStr, dealerID,
	).Scan(&avgToM); err != nil {
		return nil, fmt.Errorf("pulse.signals: avg ToM: %w", err)
	}
	if avgToM.Valid {
		s.AvgTimeOnMarket = avgToM.Float64
	}

	var priorToM sql.NullFloat64
	if err := db.QueryRowContext(ctx, `
		SELECT AVG(julianday(?) - julianday(indexed_at))
		FROM vehicle_record
		WHERE dealer_id = ? AND status = 'ACTIVE'
		  AND indexed_at >= datetime(?, '-60 days')
		  AND indexed_at <  datetime(?, '-30 days')`,
		nowStr, dealerID, nowStr, nowStr,
	).Scan(&priorToM); err != nil {
		return nil, fmt.Errorf("pulse.signals: prior ToM: %w", err)
	}
	if priorToM.Valid && priorToM.Float64 > 0 && avgToM.Valid {
		s.TimeOnMarketDelta = ((s.AvgTimeOnMarket - priorToM.Float64) / priorToM.Float64) * 100
	}

	// -- 6. Composite score delta (confidence_score pts vs prior 14d) -----------
	var recentCS, priorCS sql.NullFloat64
	if err := db.QueryRowContext(ctx, `
		SELECT
		  AVG(CASE WHEN indexed_at >= datetime(?, '-14 days') THEN confidence_score END),
		  AVG(CASE WHEN indexed_at >= datetime(?, '-28 days')
		            AND indexed_at <  datetime(?, '-14 days') THEN confidence_score END)
		FROM vehicle_record
		WHERE dealer_id = ? AND status = 'ACTIVE'`,
		nowStr, nowStr, nowStr, dealerID,
	).Scan(&recentCS, &priorCS); err != nil {
		return nil, fmt.Errorf("pulse.signals: composite delta: %w", err)
	}
	if recentCS.Valid && priorCS.Valid {
		// confidence_score is 0-1; multiply by 100 for "points" representation
		s.CompositeScoreDelta = (recentCS.Float64 - priorCS.Float64) * 100
	}

	// -- 7a. Brand HHI (Herfindahl-Hirschman Index of make_canonical) -----------
	makeRows, err := db.QueryContext(ctx, `
		SELECT make_canonical, COUNT(*) as cnt
		FROM vehicle_record
		WHERE dealer_id = ? AND status = 'ACTIVE' AND make_canonical IS NOT NULL
		GROUP BY make_canonical`,
		dealerID,
	)
	if err != nil {
		return nil, fmt.Errorf("pulse.signals: brand HHI: %w", err)
	}
	defer makeRows.Close()

	makeCounts := map[string]float64{}
	var total float64
	for makeRows.Next() {
		var mk string
		var cnt float64
		if err := makeRows.Scan(&mk, &cnt); err != nil {
			return nil, fmt.Errorf("pulse.signals: brand HHI scan: %w", err)
		}
		makeCounts[mk] = cnt
		total += cnt
	}
	if err := makeRows.Err(); err != nil {
		return nil, fmt.Errorf("pulse.signals: brand HHI rows: %w", err)
	}
	if total > 0 {
		var hhi float64
		for _, cnt := range makeCounts {
			share := cnt / total
			hhi += share * share
		}
		s.BrandHHI = hhi
	}

	// -- 7b. Price vs market ratio (dealer avg / country avg) -------------------
	var dealerAvg, marketAvg sql.NullFloat64
	if err := db.QueryRowContext(ctx, `
		SELECT
		  (SELECT AVG(price_gross_eur)
		     FROM vehicle_record
		    WHERE dealer_id = ? AND status = 'ACTIVE' AND price_gross_eur > 0),
		  (SELECT AVG(vr.price_gross_eur)
		     FROM vehicle_record vr
		     JOIN dealer_entity de ON vr.dealer_id = de.dealer_id
		    WHERE de.country_code = (SELECT country_code FROM dealer_entity WHERE dealer_id = ?)
		      AND vr.status = 'ACTIVE' AND vr.price_gross_eur > 0)`,
		dealerID, dealerID,
	).Scan(&dealerAvg, &marketAvg); err != nil {
		return nil, fmt.Errorf("pulse.signals: price vs market: %w", err)
	}
	if dealerAvg.Valid && marketAvg.Valid && marketAvg.Float64 > 0 {
		s.PriceVsMarket = dealerAvg.Float64 / marketAvg.Float64
	} else {
		s.PriceVsMarket = 1.0
	}

	return s, nil
}

// computeZScore returns the z-score of the last element in counts vs the rest.
func computeZScore(counts []float64) float64 {
	if len(counts) < 2 {
		return 0
	}
	baseline := counts[:len(counts)-1]
	current := counts[len(counts)-1]

	var sum float64
	for _, v := range baseline {
		sum += v
	}
	mean := sum / float64(len(baseline))

	var variance float64
	for _, v := range baseline {
		d := v - mean
		variance += d * d
	}
	stddev := math.Sqrt(variance / float64(len(baseline)))
	if stddev == 0 {
		return 0
	}
	return (current - mean) / stddev
}
