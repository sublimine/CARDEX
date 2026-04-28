package ev_watch

import (
	"context"
	"database/sql"
	"fmt"
	"math"
	"time"
)

// EVAnomalyScore is the result of cohort-based anomaly detection for one EV listing.
type EVAnomalyScore struct {
	ListingID       string
	VIN             string
	Make            string
	Model           string
	Year            int
	Country         string
	PriceCents      int64
	MileageKM       int
	CohortSize      int
	CohortMeanPrice int64
	CohortStdDev    float64
	ZScore          float64
	AnomalyFlag     bool    // z < -1.5
	Confidence      float64 // 0–1 based on cohort size
	EstimatedSoH    string  // "normal" | "below_average" | "suspicious"
	DetectedAt      time.Time
}

// MinCohortSize is the minimum number of listings required before z-scores are computed.
const MinCohortSize = 20

// SevereAnomalyZThreshold triggers the Prometheus severe-anomaly counter.
const SevereAnomalyZThreshold = -2.0

// SevereAnomalyCohortMin is the minimum cohort size for severe-anomaly alerts.
const SevereAnomalyCohortMin = 30

// ── Electric fuel types recognised by the normaliser ─────────────────────────

var evFuelTypes = map[string]bool{
	"electric":       true,
	"hybrid_plugin":  true,
	"plug_in_hybrid": true,
}

// ── listing is an in-memory representation of one EV listing row ──────────────

type listing struct {
	vehicleID string
	vin       string
	make      string
	model     string
	year      int
	country   string
	priceEUR  float64
	mileageKM float64
}

type cohortKey struct {
	make    string
	model   string
	year    int
	country string
}

// ── Analyzer ──────────────────────────────────────────────────────────────────

// Analyzer reads EV listings from SQLite and computes per-listing anomaly scores.
type Analyzer struct {
	db *sql.DB
}

// NewAnalyzer creates an Analyzer backed by db.
func NewAnalyzer(db *sql.DB) *Analyzer { return &Analyzer{db: db} }

// RunAnalysis computes anomaly scores for all EV cohorts with >= MinCohortSize listings,
// persists results to ev_anomaly_scores, and returns the scored records.
func (a *Analyzer) RunAnalysis(ctx context.Context) ([]EVAnomalyScore, error) {
	if err := EnsureSchema(a.db); err != nil {
		return nil, fmt.Errorf("ev_watch: ensure schema: %w", err)
	}

	listings, err := a.loadEVListings(ctx)
	if err != nil {
		return nil, fmt.Errorf("ev_watch: load listings: %w", err)
	}

	cohorts := groupByCohort(listings)
	var allScores []EVAnomalyScore
	for _, members := range cohorts {
		if len(members) < MinCohortSize {
			continue
		}
		scores := analyzeOneCohort(members)
		allScores = append(allScores, scores...)
	}

	if err := a.persistScores(ctx, allScores); err != nil {
		return nil, fmt.Errorf("ev_watch: persist scores: %w", err)
	}

	for _, s := range allScores {
		if s.AnomalyFlag {
			metricAnomaliesDetected.Inc()
		}
		if s.ZScore < SevereAnomalyZThreshold && s.CohortSize >= SevereAnomalyCohortMin {
			metricSevereAnomalies.Inc()
		}
	}

	return allScores, nil
}

// loadEVListings queries vehicle_record for EV listings with valid price + mileage.
func (a *Analyzer) loadEVListings(ctx context.Context) ([]listing, error) {
	rows, err := a.db.QueryContext(ctx, `
		SELECT
			vr.vehicle_id,
			COALESCE(vr.vin, ''),
			UPPER(COALESCE(vr.make_canonical, '')),
			UPPER(COALESCE(vr.model_canonical, '')),
			COALESCE(vr.year, 0),
			UPPER(COALESCE(de.country_code, '')),
			COALESCE(vr.price_gross_eur, vr.price_net_eur, 0),
			COALESCE(vr.mileage_km, 0),
			LOWER(COALESCE(vr.fuel_type, ''))
		FROM vehicle_record vr
		LEFT JOIN dealer_entity de ON de.dealer_id = vr.dealer_id
		WHERE vr.price_gross_eur > 0
		  AND vr.mileage_km > 0
		  AND vr.make_canonical IS NOT NULL
		  AND vr.model_canonical IS NOT NULL
		  AND vr.year > 0
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []listing
	for rows.Next() {
		var l listing
		var fuelType string
		if err := rows.Scan(
			&l.vehicleID, &l.vin, &l.make, &l.model,
			&l.year, &l.country, &l.priceEUR, &l.mileageKM, &fuelType,
		); err != nil {
			return nil, err
		}
		if evFuelTypes[fuelType] {
			out = append(out, l)
		}
	}
	return out, rows.Err()
}

// groupByCohort organises listings by (make, model, year, country).
func groupByCohort(listings []listing) map[cohortKey][]listing {
	m := make(map[cohortKey][]listing)
	for _, l := range listings {
		k := cohortKey{make: l.make, model: l.model, year: l.year, country: l.country}
		m[k] = append(m[k], l)
	}
	return m
}

// analyzeOneCohort computes z-scores for all members of one cohort.
// Assumes len(members) >= MinCohortSize.
func analyzeOneCohort(members []listing) []EVAnomalyScore {
	n := len(members)

	// Extract price and mileage vectors.
	prices := make([]float64, n)
	miles := make([]float64, n)
	for i, m := range members {
		prices[i] = m.priceEUR
		miles[i] = m.mileageKM
	}

	// Fit price ~ mileage_km OLS regression.
	slope, intercept := olsRegression(miles, prices)

	// Compute residuals: price - predicted_price.
	residuals := make([]float64, n)
	for i := range members {
		predicted := intercept + slope*miles[i]
		residuals[i] = prices[i] - predicted
	}

	meanRes := mean(residuals)
	stdRes := stddev(residuals, meanRes)

	cohortMeanPrice := mean(prices)
	cohortStdDev := stddev(prices, cohortMeanPrice)

	confidence := cohortConfidence(n)
	now := time.Now().UTC()

	scores := make([]EVAnomalyScore, n)
	for i, l := range members {
		z := 0.0
		if stdRes > 1e-9 {
			z = (residuals[i] - meanRes) / stdRes
		}
		flag := z < -1.5
		soh := estimateSoH(z)

		scores[i] = EVAnomalyScore{
			ListingID:       l.vehicleID,
			VIN:             l.vin,
			Make:            l.make,
			Model:           l.model,
			Year:            l.year,
			Country:         l.country,
			PriceCents:      int64(math.Round(l.priceEUR * 100)),
			MileageKM:       int(l.mileageKM),
			CohortSize:      n,
			CohortMeanPrice: int64(math.Round(cohortMeanPrice * 100)),
			CohortStdDev:    cohortStdDev,
			ZScore:          z,
			AnomalyFlag:     flag,
			Confidence:      confidence,
			EstimatedSoH:    soh,
			DetectedAt:      now,
		}
	}
	return scores
}

// persistScores upserts anomaly scores into ev_anomaly_scores.
func (a *Analyzer) persistScores(ctx context.Context, scores []EVAnomalyScore) error {
	if len(scores) == 0 {
		return nil
	}
	tx, err := a.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback() //nolint:errcheck

	stmt, err := tx.PrepareContext(ctx, `
		INSERT INTO ev_anomaly_scores
		    (vehicle_id, vin, make, model, year, country,
		     price_cents, mileage_km, cohort_size, cohort_mean_price,
		     cohort_std_dev, z_score, anomaly_flag, confidence,
		     estimated_soh, detected_at)
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
		ON CONFLICT(vehicle_id) DO UPDATE SET
		    cohort_size       = excluded.cohort_size,
		    cohort_mean_price = excluded.cohort_mean_price,
		    cohort_std_dev    = excluded.cohort_std_dev,
		    z_score           = excluded.z_score,
		    anomaly_flag      = excluded.anomaly_flag,
		    confidence        = excluded.confidence,
		    estimated_soh     = excluded.estimated_soh,
		    detected_at       = excluded.detected_at
	`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, s := range scores {
		anomalyInt := 0
		if s.AnomalyFlag {
			anomalyInt = 1
		}
		if _, err := stmt.ExecContext(ctx,
			s.ListingID, s.VIN, s.Make, s.Model, s.Year, s.Country,
			s.PriceCents, s.MileageKM, s.CohortSize, s.CohortMeanPrice,
			s.CohortStdDev, s.ZScore, anomalyInt, s.Confidence,
			s.EstimatedSoH, s.DetectedAt.Format(time.RFC3339),
		); err != nil {
			return fmt.Errorf("insert %s: %w", s.ListingID, err)
		}
	}
	return tx.Commit()
}

// ── Math helpers ──────────────────────────────────────────────────────────────

// olsRegression returns (slope, intercept) for y = intercept + slope*x.
func olsRegression(x, y []float64) (slope, intercept float64) {
	n := float64(len(x))
	if n < 2 {
		return 0, mean(y)
	}
	sumX, sumY, sumXY, sumXX := 0.0, 0.0, 0.0, 0.0
	for i := range x {
		sumX += x[i]
		sumY += y[i]
		sumXY += x[i] * y[i]
		sumXX += x[i] * x[i]
	}
	denom := n*sumXX - sumX*sumX
	if math.Abs(denom) < 1e-9 {
		return 0, sumY / n
	}
	slope = (n*sumXY - sumX*sumY) / denom
	intercept = (sumY - slope*sumX) / n
	return
}

func mean(v []float64) float64 {
	if len(v) == 0 {
		return 0
	}
	s := 0.0
	for _, x := range v {
		s += x
	}
	return s / float64(len(v))
}

func stddev(v []float64, m float64) float64 {
	if len(v) < 2 {
		return 0
	}
	s := 0.0
	for _, x := range v {
		d := x - m
		s += d * d
	}
	return math.Sqrt(s / float64(len(v)))
}

func cohortConfidence(n int) float64 {
	return math.Min(1.0, float64(n)/100.0)
}

func estimateSoH(z float64) string {
	switch {
	case z < SevereAnomalyZThreshold:
		return "suspicious"
	case z < -1.5:
		return "below_average"
	default:
		return "normal"
	}
}
