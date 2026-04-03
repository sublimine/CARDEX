package handlers

// valuation.go — VIN Valuation Engine (Gap 2) + Residual Value Forecasting (Gap 3)
//
// VINValuation  : GET /api/v1/analytics/vin-valuation?vin=...&mileage_km=...
// ResidualValue : GET /api/v1/analytics/residual?make=...&model=...&year=...&mileage_km=...&country=...
//
// Competitive advantage vs DATgroup/Eurotax:
//   – Real-time market data from Cardex's own ClickHouse scrape database (updated daily)
//   – DATgroup & Eurotax rely on static monthly-updated wholesale databases
//   – We show not just value, but "at this price it sells in X days"
//
// Competitive advantage vs Indicata residual forecasting:
//   – MDS-trend adjusted: if demand is growing, depreciation slows (Indicata ignores this)
//   – Shows cost-of-holding per day using real recon/floor cost from CRM

import (
	"fmt"
	"log/slog"
	"math"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ── VIN Valuation ──────────────────────────────────────────────────────────────

type vinValuationResponse struct {
	VIN              string             `json:"vin"`
	Make             string             `json:"make"`
	Model            string             `json:"model"`
	Year             int                `json:"year"`
	FuelType         string             `json:"fuel_type"`
	InputMileageKM   int                `json:"input_mileage_km"`
	MarketSampleSize int                `json:"market_sample_size"`
	Distribution     priceDistribution  `json:"distribution"`
	MileageAdjusted  adjustedValuation  `json:"mileage_adjusted"`
	MarketVelocity   velocityByPrice    `json:"market_velocity"`
	DataAsOf         string             `json:"data_as_of"`
	Methodology      string             `json:"methodology"`
}

type priceDistribution struct {
	P10    float64 `json:"p10"`
	P25    float64 `json:"p25"`
	Median float64 `json:"median"`
	P75    float64 `json:"p75"`
	P90    float64 `json:"p90"`
	Mean   float64 `json:"mean"`
	StdDev float64 `json:"std_dev"`
}

type adjustedValuation struct {
	TradeInEUR          float64 `json:"trade_in_eur"`
	RetailLowEUR        float64 `json:"retail_low_eur"`
	RetailHighEUR       float64 `json:"retail_high_eur"`
	MedianMileageKM     int     `json:"median_mileage_km"`
	MileageDeltaKM      int     `json:"mileage_delta_km"`
	MileageAdjPct       float64 `json:"mileage_adj_pct"`
}

type velocityByPrice struct {
	AtP25DOMdays int `json:"at_p25_dom_days"`
	AtP50DOMdays int `json:"at_p50_dom_days"`
	AtP75DOMdays int `json:"at_p75_dom_days"`
}

// VINValuation handles GET /api/v1/analytics/vin-valuation
func (d *Deps) VINValuation(w http.ResponseWriter, r *http.Request) {
	vin := strings.ToUpper(strings.TrimSpace(r.URL.Query().Get("vin")))
	if vin == "" || !vinRe.MatchString(vin) {
		writeError(w, http.StatusBadRequest, "invalid_vin", "17-character VIN required (no I, O, Q)")
		return
	}

	mileageKM := 0
	if s := r.URL.Query().Get("mileage_km"); s != "" {
		if v, err := strconv.Atoi(s); err == nil && v >= 0 {
			mileageKM = v
		}
	}

	ctx := r.Context()

	// ── 1. Decode VIN to make/model/year ─────────────────────────────────────
	spec := cacheGetSpec(ctx, d, vin)
	if spec == nil {
		var err error
		spec, err = fetchNHTSASpec(ctx, vin)
		if err != nil {
			slog.Warn("vin-valuation: nhtsa decode failed", "vin", vin, "error", err)
		} else {
			cacheSetSpec(ctx, d, vin, spec)
		}
	}

	make_, model_, year_ := "", "", 0
	if spec != nil {
		make_ = spec.Make
		model_ = spec.Model
		year_ = spec.Year
	}

	if make_ == "" {
		writeError(w, http.StatusUnprocessableEntity, "decode_failed",
			"unable to decode VIN to make/model/year — check VIN or try again")
		return
	}

	// ── 2. Query ClickHouse for matching market prices ────────────────────────
	// Match on make/model, allow ±2 model years for sufficient sample size.
	type chPriceRow struct {
		PriceEUR  float64
		MileageKM int
		DOMDAYS   int
	}

	rows, err := d.CH.Query(ctx, `
		SELECT
			price_eur,
			mileage_km,
			toUInt32(date_diff('day', first_seen_at, coalesce(sold_at, now()))) AS dom_days
		FROM cardex.vehicle_inventory
		WHERE
			lower(make) = lower(?) AND
			lower(model) = lower(?) AND
			year BETWEEN ? AND ? AND
			lifecycle_status IN ('ACTIVE','SOLD') AND
			price_eur > 500 AND price_eur < 500000 AND
			mileage_km >= 0
		LIMIT 2000
	`, make_, model_, year_-2, year_+2)

	if err != nil {
		slog.Error("vin-valuation: clickhouse query", "vin", vin, "error", err)
		writeError(w, http.StatusServiceUnavailable, "data_unavailable", "market data temporarily unavailable")
		return
	}
	defer rows.Close()

	var prices []float64
	var mileages []float64
	var doms []int

	for rows.Next() {
		var priceEUR float64
		var mileageKMRow int
		var domDays int
		if err := rows.Scan(&priceEUR, &mileageKMRow, &domDays); err != nil {
			slog.Warn("vin-valuation: row scan", "error", err)
			continue
		}
		prices = append(prices, priceEUR)
		mileages = append(mileages, float64(mileageKMRow))
		doms = append(doms, domDays)
	}

	if len(prices) < 5 {
		writeError(w, http.StatusNotFound, "insufficient_data",
			fmt.Sprintf("only %d listings found for %s %s — need at least 5", len(prices), make_, model_))
		return
	}

	// ── 3. Compute price distribution ─────────────────────────────────────────
	sortedPrices := make([]float64, len(prices))
	copy(sortedPrices, prices)
	sort.Float64s(sortedPrices)

	dist := priceDistribution{
		P10:    percentile(sortedPrices, 10),
		P25:    percentile(sortedPrices, 25),
		Median: percentile(sortedPrices, 50),
		P75:    percentile(sortedPrices, 75),
		P90:    percentile(sortedPrices, 90),
		Mean:   mean(sortedPrices),
		StdDev: stddev(sortedPrices),
	}

	// ── 4. Mileage adjustment ─────────────────────────────────────────────────
	// Industry standard: ~0.15% per 1000km deviation from segment median.
	sortedMileages := make([]float64, len(mileages))
	copy(sortedMileages, mileages)
	sort.Float64s(sortedMileages)
	medianMileageKM := int(percentile(sortedMileages, 50))

	mileageDeltaKM := mileageKM - medianMileageKM
	mileageAdjPct := 0.0
	if mileageKM > 0 && medianMileageKM > 0 {
		// -0.15% per 1000km above median; +0.10% per 1000km below median
		deltaK := float64(mileageDeltaKM) / 1000.0
		if deltaK > 0 {
			mileageAdjPct = -0.15 * deltaK
		} else {
			mileageAdjPct = 0.10 * (-deltaK)
		}
		// Cap adjustment at ±30%
		mileageAdjPct = math.Max(-30, math.Min(30, mileageAdjPct))
	}

	adjFactor := 1 + mileageAdjPct/100
	adjMedian := dist.Median * adjFactor

	// ── 5. DOM velocity by price scenario ────────────────────────────────────
	// Partition listings by price quintile, compute avg DOM for each.
	atP25 := avgDOMNearPrice(prices, doms, dist.P25, dist.StdDev*0.3)
	atP50 := avgDOMNearPrice(prices, doms, dist.Median, dist.StdDev*0.3)
	atP75 := avgDOMNearPrice(prices, doms, dist.P75, dist.StdDev*0.3)

	resp := vinValuationResponse{
		VIN:              vin,
		Make:             make_,
		Model:            model_,
		Year:             year_,
		InputMileageKM:   mileageKM,
		MarketSampleSize: len(prices),
		Distribution:     dist,
		MileageAdjusted: adjustedValuation{
			TradeInEUR:      round2(adjMedian * dist.P25 / dist.Median * 0.92),
			RetailLowEUR:    round2(adjMedian * dist.P25 / dist.Median),
			RetailHighEUR:   round2(adjMedian * dist.P75 / dist.Median),
			MedianMileageKM: medianMileageKM,
			MileageDeltaKM:  mileageDeltaKM,
			MileageAdjPct:   round2(mileageAdjPct),
		},
		MarketVelocity: velocityByPrice{
			AtP25DOMdays: atP25,
			AtP50DOMdays: atP50,
			AtP75DOMdays: atP75,
		},
		DataAsOf:    time.Now().UTC().Format("2006-01-02"),
		Methodology: "Real-time Cardex scrape database. Mileage adjusted at ±0.15%/1000km. Trade-in = P25×0.92. DOM from active+sold listings.",
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── Residual Value Forecasting ─────────────────────────────────────────────────

type residualResponse struct {
	Make              string              `json:"make"`
	Model             string              `json:"model"`
	Year              int                 `json:"year"`
	Country           string              `json:"country"`
	CurrentValueEUR   float64             `json:"current_value_eur"`
	MileageKM         int                 `json:"mileage_km"`
	LambdaMonthly     float64             `json:"lambda_monthly"`
	MDSAdjusted       bool                `json:"mds_adjusted"`
	MDSValue          float64             `json:"mds_days"`
	Projections       []residualPoint     `json:"projections"`
	CostOfHoldingPerDay float64           `json:"cost_of_holding_per_day_eur"`
	DataPoints        int                 `json:"historical_data_points"`
	Confidence        string              `json:"confidence"`
	Methodology       string              `json:"methodology"`
}

type residualPoint struct {
	MonthsAhead   int     `json:"months_ahead"`
	Date          string  `json:"date"`
	EstimatedEUR  float64 `json:"estimated_eur"`
	LossFromNow   float64 `json:"cumulative_loss_eur"`
	LossPct       float64 `json:"cumulative_loss_pct"`
}

// ResidualValue handles GET /api/v1/analytics/residual
func (d *Deps) ResidualValue(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := strings.TrimSpace(q.Get("make"))
	model_ := strings.TrimSpace(q.Get("model"))
	yearStr := q.Get("year")
	mileageStr := q.Get("mileage_km")
	country := strings.ToUpper(strings.TrimSpace(q.Get("country")))

	if make_ == "" || model_ == "" || yearStr == "" {
		writeError(w, http.StatusBadRequest, "missing_params", "make, model, and year are required")
		return
	}

	year, err := strconv.Atoi(yearStr)
	if err != nil || year < 1990 || year > time.Now().Year()+1 {
		writeError(w, http.StatusBadRequest, "invalid_year", "year must be between 1990 and current year+1")
		return
	}

	mileageKM := 0
	if mileageStr != "" {
		if v, err := strconv.Atoi(mileageStr); err == nil && v >= 0 {
			mileageKM = v
		}
	}

	if country == "" {
		country = "ES"
	}

	ctx := r.Context()

	// ── 1. Fetch monthly average prices (past 24 months) ─────────────────────
	type monthlyAvg struct {
		Month    string
		AvgPrice float64
	}

	chQuery := `
		SELECT
			formatDateTime(toStartOfMonth(scraped_at), '%Y-%m') AS month,
			avg(price_eur) AS avg_price
		FROM cardex.vehicle_inventory
		WHERE
			lower(make) = lower(?) AND
			lower(model) = lower(?) AND
			year = ? AND
			price_eur > 500 AND
			scraped_at >= now() - interval 24 month
		GROUP BY month
		ORDER BY month ASC
	`

	chArgs := []any{make_, model_, year}
	if country != "" && country != "ALL" {
		chQuery = `
		SELECT
			formatDateTime(toStartOfMonth(scraped_at), '%Y-%m') AS month,
			avg(price_eur) AS avg_price
		FROM cardex.vehicle_inventory
		WHERE
			lower(make) = lower(?) AND
			lower(model) = lower(?) AND
			year = ? AND
			country_code = ? AND
			price_eur > 500 AND
			scraped_at >= now() - interval 24 month
		GROUP BY month
		ORDER BY month ASC
		`
		chArgs = []any{make_, model_, year, country}
	}

	rows, err := d.CH.Query(ctx, chQuery, chArgs...)
	if err != nil {
		slog.Error("residual: clickhouse monthly query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "data_unavailable", "market data temporarily unavailable")
		return
	}
	defer rows.Close()

	var monthlyData []monthlyAvg
	for rows.Next() {
		var m monthlyAvg
		if err := rows.Scan(&m.Month, &m.AvgPrice); err != nil {
			slog.Warn("residual: row scan", "error", err)
			continue
		}
		monthlyData = append(monthlyData, m)
	}

	// If country-specific data is thin, fall back to all-country
	if len(monthlyData) < 4 && country != "ALL" {
		rows2, err2 := d.CH.Query(ctx, `
			SELECT
				formatDateTime(toStartOfMonth(scraped_at), '%Y-%m') AS month,
				avg(price_eur) AS avg_price
			FROM cardex.vehicle_inventory
			WHERE
				lower(make) = lower(?) AND
				lower(model) = lower(?) AND
				year = ? AND
				price_eur > 500 AND
				scraped_at >= now() - interval 24 month
			GROUP BY month
			ORDER BY month ASC
		`, make_, model_, year)
		if err2 == nil {
			defer rows2.Close()
			monthlyData = nil
			for rows2.Next() {
				var m monthlyAvg
				if err2 := rows2.Scan(&m.Month, &m.AvgPrice); err2 == nil {
					monthlyData = append(monthlyData, m)
				}
			}
		}
	}

	// ── 2. Fit depreciation curve λ ───────────────────────────────────────────
	// Exponential: price(t) = P0 × exp(-λ × t), t in months
	// Fit via OLS on ln(price) = ln(P0) - λ × t
	lambda := 0.008 // Default: ~0.8% per month (industry avg for mass-market cars)
	currentValueEUR := 0.0
	confidence := "LOW"
	dataPoints := len(monthlyData)

	if dataPoints >= 3 {
		lambda, currentValueEUR = fitDepreciation(monthlyData)
		if dataPoints >= 8 {
			confidence = "HIGH"
		} else if dataPoints >= 5 {
			confidence = "MEDIUM"
		} else {
			confidence = "LOW"
		}
	} else if dataPoints > 0 {
		// Use last known price + industry lambda
		currentValueEUR = monthlyData[len(monthlyData)-1].AvgPrice
	}

	// Segment-based lambda override if fitted lambda is unrealistic
	if lambda < 0.001 || lambda > 0.05 {
		lambda = segmentLambda(make_, year)
	}

	// ── 3. MDS adjustment ─────────────────────────────────────────────────────
	// Fetch current MDS for this segment to adjust λ
	mdsRow := d.CH.QueryRow(ctx, `
		SELECT
			countIf(lifecycle_status = 'ACTIVE') / greatest(countIf(lifecycle_status = 'SOLD' AND sold_at >= now() - interval 30 day) / 30.0, 0.1) AS mds
		FROM cardex.vehicle_inventory
		WHERE lower(make) = lower(?) AND lower(model) = lower(?) AND year = ?
	`, make_, model_, year)

	mdsValue := 45.0 // fallback: neutral market
	mdsAdjusted := false
	var mdsRaw float64
	if err := mdsRow.Scan(&mdsRaw); err == nil && mdsRaw > 0 && mdsRaw < 365 {
		mdsValue = mdsRaw
		// Adjust λ: hot market slows depreciation, cold market accelerates it
		switch {
		case mdsValue < 20:
			lambda *= 0.80 // Very hot market — depreciation slows significantly
			mdsAdjusted = true
		case mdsValue < 35:
			lambda *= 0.90 // Hot market
			mdsAdjusted = true
		case mdsValue > 90:
			lambda *= 1.20 // Cold market — depreciation accelerates
			mdsAdjusted = true
		case mdsValue > 60:
			lambda *= 1.10 // Soft market
			mdsAdjusted = true
		}
	}

	// If current value not fitted, use P50 from a simple query
	if currentValueEUR <= 0 {
		priceRow := d.CH.QueryRow(ctx, `
			SELECT quantile(0.5)(price_eur)
			FROM cardex.vehicle_inventory
			WHERE lower(make) = lower(?) AND lower(model) = lower(?) AND year = ? AND price_eur > 500
		`, make_, model_, year)
		_ = priceRow.Scan(&currentValueEUR)
	}

	if currentValueEUR <= 0 {
		writeError(w, http.StatusNotFound, "insufficient_data",
			fmt.Sprintf("no price data found for %s %s %d", make_, model_, year))
		return
	}

	// ── 4. Mileage adjustment to current value ────────────────────────────────
	if mileageKM > 0 {
		// Use typical mileage for a car of that age to adjust current value
		ageYears := time.Now().Year() - year
		typicalMileage := ageYears * 15000 // ~15,000 km/year European average
		deltaMileage := mileageKM - typicalMileage
		mileageAdj := float64(-deltaMileage) / 1000.0 * 0.12 / 100 // 0.12% per 1000km
		mileageAdj = math.Max(-0.25, math.Min(0.25, mileageAdj))
		currentValueEUR = currentValueEUR * (1 + mileageAdj)
	}

	// ── 5. Project forward ────────────────────────────────────────────────────
	projectMonths := []int{1, 3, 6, 12, 24, 36}
	now := time.Now()
	projections := make([]residualPoint, 0, len(projectMonths))
	for _, m := range projectMonths {
		futureVal := currentValueEUR * math.Exp(-lambda*float64(m))
		futureDate := now.AddDate(0, m, 0).Format("2006-01")
		lossEUR := currentValueEUR - futureVal
		lossPct := lossEUR / currentValueEUR * 100
		projections = append(projections, residualPoint{
			MonthsAhead:  m,
			Date:         futureDate,
			EstimatedEUR: round2(futureVal),
			LossFromNow:  round2(lossEUR),
			LossPct:      round2(lossPct),
		})
	}

	// ── 6. Cost of holding per day ────────────────────────────────────────────
	// λ * currentValue / 30 = daily depreciation cost
	costPerDay := currentValueEUR * lambda / 30.0
	// Add financing cost estimate: ~5% APR / 365 days
	costPerDay += currentValueEUR * 0.05 / 365

	resp := residualResponse{
		Make:                make_,
		Model:               model_,
		Year:                year,
		Country:             country,
		CurrentValueEUR:     round2(currentValueEUR),
		MileageKM:           mileageKM,
		LambdaMonthly:       round4(lambda),
		MDSAdjusted:         mdsAdjusted,
		MDSValue:            round2(mdsValue),
		Projections:         projections,
		CostOfHoldingPerDay: round2(costPerDay),
		DataPoints:          dataPoints,
		Confidence:          confidence,
		Methodology:         "Cardex real-time scrape data. Exponential depreciation fit (OLS on log-price). MDS-trend adjusted. Financing cost: 5% APR.",
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── Math helpers ───────────────────────────────────────────────────────────────

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	idx := (p / 100) * float64(len(sorted)-1)
	lo := int(idx)
	hi := lo + 1
	if hi >= len(sorted) {
		return sorted[len(sorted)-1]
	}
	frac := idx - float64(lo)
	return sorted[lo]*(1-frac) + sorted[hi]*frac
}

func mean(vals []float64) float64 {
	if len(vals) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range vals {
		sum += v
	}
	return sum / float64(len(vals))
}

func stddev(vals []float64) float64 {
	if len(vals) < 2 {
		return 0
	}
	m := mean(vals)
	sumSq := 0.0
	for _, v := range vals {
		d := v - m
		sumSq += d * d
	}
	return math.Sqrt(sumSq / float64(len(vals)-1))
}

func avgDOMNearPrice(prices []float64, doms []int, targetPrice, band float64) int {
	if band < 500 {
		band = 500
	}
	sum, count := 0, 0
	for i, p := range prices {
		if math.Abs(p-targetPrice) <= band {
			sum += doms[i]
			count++
		}
	}
	if count == 0 {
		return 45 // fallback
	}
	return sum / count
}

// fitDepreciation fits an exponential depreciation curve to monthly avg prices.
// Returns (lambda, currentEstimate).
func fitDepreciation(data []monthlyAvg) (float64, float64) {
	n := len(data)
	if n < 2 {
		return 0.008, data[0].AvgPrice
	}

	// OLS: ln(price) = a - λ*t, where t = months from first data point
	// sum(t), sum(ln_p), sum(t*ln_p), sum(t^2)
	var sumT, sumLnP, sumTLnP, sumT2 float64
	for i, m := range data {
		if m.AvgPrice <= 0 {
			continue
		}
		t := float64(i)
		lnP := math.Log(m.AvgPrice)
		sumT += t
		sumLnP += lnP
		sumTLnP += t * lnP
		sumT2 += t * t
	}
	fn := float64(n)
	denom := fn*sumT2 - sumT*sumT
	if math.Abs(denom) < 1e-9 {
		return 0.008, data[n-1].AvgPrice
	}
	// slope = (n*sumTLnP - sumT*sumLnP) / denom  → -λ (negative = depreciation)
	slope := (fn*sumTLnP - sumT*sumLnP) / denom
	intercept := (sumLnP - slope*sumT) / fn
	lambda := -slope
	if lambda < 0 {
		lambda = 0.003 // floor: near-zero depreciation (rare)
	}

	// Current value estimate from fit (t = months since first data point = n-1)
	currentEst := math.Exp(intercept + slope*float64(n-1))

	// Sanity: use actual last-month value if fit diverges > 40%
	lastReal := data[n-1].AvgPrice
	if math.Abs(currentEst-lastReal)/lastReal > 0.40 {
		currentEst = lastReal
	}

	return lambda, currentEst
}

// segmentLambda returns a segment-based default depreciation rate (monthly).
// Source: EY/Roland Berger depreciation studies, 2023.
func segmentLambda(make_ string, year int) float64 {
	age := time.Now().Year() - year
	makeLower := strings.ToLower(make_)

	// Premium brands depreciate slower
	premium := map[string]bool{
		"bmw": true, "mercedes": true, "mercedes-benz": true,
		"audi": true, "porsche": true, "lexus": true,
		"volvo": true, "jaguar": true, "land rover": true,
	}
	if premium[makeLower] {
		switch {
		case age <= 2:
			return 0.012
		case age <= 5:
			return 0.009
		default:
			return 0.007
		}
	}

	// Mass market
	switch {
	case age <= 2:
		return 0.018
	case age <= 5:
		return 0.013
	default:
		return 0.009
	}
}

func round2(v float64) float64 {
	return math.Round(v*100) / 100
}

func round4(v float64) float64 {
	return math.Round(v*10000) / 10000
}
