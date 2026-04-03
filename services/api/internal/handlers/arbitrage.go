package handlers

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cardex/alpha/pkg/nlc"
	"github.com/cardex/api/internal/middleware"
	"github.com/redis/go-redis/v9"
)

// ── Types ─────────────────────────────────────────────────────────────────────

type arbitrageOpportunity struct {
	OpportunityID     string  `json:"opportunity_id"`
	ScannedAt         string  `json:"scanned_at"`
	OpportunityType   string  `json:"opportunity_type"`
	Make              string  `json:"make"`
	Model             string  `json:"model"`
	Year              uint16  `json:"year"`
	FuelType          string  `json:"fuel_type"`
	OriginCountry     string  `json:"origin_country"`
	DestCountry       string  `json:"dest_country"`
	OriginMedianEUR   float64 `json:"origin_median_eur"`
	DestMedianEUR     float64 `json:"dest_median_eur"`
	NLCEstimateEUR    float64 `json:"nlc_estimate_eur"`
	GrossMarginEUR    float64 `json:"gross_margin_eur"`
	MarginPct         float32 `json:"margin_pct"`
	ConfidenceScore   float32 `json:"confidence_score"`
	SampleSizeOrigin  uint32  `json:"sample_size_origin"`
	SampleSizeDest    uint32  `json:"sample_size_dest"`
	CO2GKM            uint16  `json:"co2_gkm"`
	BPMRefundEUR      float64 `json:"bpm_refund_eur"`
	IEDMTEUR          float64 `json:"iedmt_eur"`
	MalusEUR          float64 `json:"malus_eur"`
	ExampleListingURL string  `json:"example_listing_url"`
	Status            string  `json:"status"`
}

type arbitrageRouteStats struct {
	RouteKey         string  `json:"route_key"`
	OriginCountry    string  `json:"origin_country"`
	DestCountry      string  `json:"dest_country"`
	Make             string  `json:"make"`
	ModelFamily      string  `json:"model_family"`
	FuelType         string  `json:"fuel_type"`
	AvgMarginEUR     float64 `json:"avg_margin_eur"`
	AvgMarginPct     float32 `json:"avg_margin_pct"`
	OpportunityCount uint32  `json:"opportunity_count"`
	AvgConfidence    float32 `json:"avg_confidence"`
	LastUpdated      string  `json:"last_updated"`
}

type nlcBreakdown struct {
	LogisticsEUR float64 `json:"logistics_eur"`
	OriginTaxEUR float64 `json:"origin_tax_eur"`
	DestTaxEUR   float64 `json:"dest_tax_eur"`
	TotalNLCEUR  float64 `json:"total_nlc_eur"`
	TaxType      string  `json:"tax_type"`
	TaxRatePct   float64 `json:"tax_rate_pct"`
	CO2GKM       int     `json:"co2_gkm"`
}

type nlcBreakdownResponse struct {
	Ticker          string       `json:"ticker"`
	Origin          string       `json:"origin"`
	Dest            string       `json:"dest"`
	OriginMedianEUR float64      `json:"origin_median_eur"`
	DestMedianEUR   float64      `json:"dest_median_eur"`
	NLCBreakdown    nlcBreakdown `json:"nlc_breakdown"`
	GrossMarginEUR  float64      `json:"gross_margin_eur"`
	MarginPct       float64      `json:"margin_pct"`
	Recommendation  string       `json:"recommendation"`
}

// ── ArbitrageOpportunities ────────────────────────────────────────────────────

// ArbitrageOpportunities handles GET /api/v1/arbitrage/opportunities
// Query params: type, origin, dest, make, min_margin, min_confidence, sort, limit
func (d *Deps) ArbitrageOpportunities(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	oppType := q.Get("type")
	origin := strings.ToUpper(strings.TrimSpace(q.Get("origin")))
	dest := strings.ToUpper(strings.TrimSpace(q.Get("dest")))
	make_ := q.Get("make")
	minMarginStr := q.Get("min_margin")
	minConfStr := q.Get("min_confidence")
	sortBy := q.Get("sort")
	limitStr := q.Get("limit")

	minConf := parseFloat(minConfStr, 0.5)
	if minConf < 0 || minConf > 1 {
		minConf = 0.5
	}
	limit := parseInt(limitStr, 20)
	if limit > 100 {
		limit = 100
	}
	if limit < 1 {
		limit = 1
	}

	// Validate sort column against allowlist
	allowedSorts := map[string]string{
		"margin_eur": "gross_margin_eur",
		"margin_pct": "margin_pct",
		"confidence": "confidence_score",
		"scanned_at": "scanned_at",
	}
	sortCol, ok := allowedSorts[sortBy]
	if !ok {
		sortCol = "gross_margin_eur"
	}

	// Build deterministic cache key from all params
	cacheKey := fmt.Sprintf("arbitrage:opps:%x", sha256.Sum256([]byte(
		strings.Join([]string{oppType, origin, dest, make_, minMarginStr, minConfStr, sortBy, limitStr}, "|"),
	)))

	// Try Redis cache first (5-min TTL)
	if cached, err := d.Redis.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.WriteHeader(http.StatusOK)
		w.Write(cached)
		return
	}

	var where []string
	var args []any
	where = append(where, "status = 'ACTIVE'")
	where = append(where, "scanned_at > now() - INTERVAL 48 HOUR")
	where = append(where, "confidence_score >= ?")
	args = append(args, float32(minConf))

	if oppType != "" {
		types := strings.Split(oppType, ",")
		var typeFilters []string
		for _, t := range types {
			t = strings.TrimSpace(t)
			if t != "" && isAlphaUnderscore(t) {
				typeFilters = append(typeFilters, "?")
				args = append(args, t)
			}
		}
		if len(typeFilters) > 0 {
			where = append(where, "opportunity_type IN ("+strings.Join(typeFilters, ",")+")")
		}
	}
	if origin != "" && len(origin) == 2 && isAlpha(origin) {
		where = append(where, "origin_country = ?")
		args = append(args, origin)
	}
	if dest != "" && len(dest) == 2 && isAlpha(dest) {
		where = append(where, "dest_country = ?")
		args = append(args, dest)
	}
	if make_ != "" && len(make_) <= 80 && !strings.ContainsAny(make_, `"'\\`) {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if minMarginStr != "" {
		if v, err := strconv.ParseFloat(minMarginStr, 64); err == nil && v >= 0 {
			where = append(where, "gross_margin_eur >= ?")
			args = append(args, v)
		}
	}

	query := "SELECT opportunity_id, scanned_at, opportunity_type, make, model, year, fuel_type," +
		" origin_country, dest_country, origin_median_eur, dest_median_eur, nlc_estimate_eur," +
		" gross_margin_eur, margin_pct, confidence_score, sample_size_origin, sample_size_dest," +
		" co2_gkm, bpm_refund_eur, iedmt_eur, malus_eur, example_listing_url, status" +
		" FROM cardex.arbitrage_opportunities" +
		" WHERE " + strings.Join(where, " AND ") +
		" ORDER BY " + sortCol + " DESC" +
		" LIMIT ?"
	args = append(args, limit)

	rows, err := d.CH.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	opportunities := make([]arbitrageOpportunity, 0, limit)
	for rows.Next() {
		var o arbitrageOpportunity
		var scannedAt time.Time
		if err := rows.Scan(
			&o.OpportunityID, &scannedAt, &o.OpportunityType,
			&o.Make, &o.Model, &o.Year, &o.FuelType,
			&o.OriginCountry, &o.DestCountry,
			&o.OriginMedianEUR, &o.DestMedianEUR, &o.NLCEstimateEUR,
			&o.GrossMarginEUR, &o.MarginPct, &o.ConfidenceScore,
			&o.SampleSizeOrigin, &o.SampleSizeDest,
			&o.CO2GKM, &o.BPMRefundEUR, &o.IEDMTEUR, &o.MalusEUR,
			&o.ExampleListingURL, &o.Status,
		); err != nil {
			continue
		}
		o.ScannedAt = scannedAt.Format(time.RFC3339)
		opportunities = append(opportunities, o)
	}

	resp := map[string]any{
		"opportunities": opportunities,
		"count":         len(opportunities),
		"filters": map[string]any{
			"type":           oppType,
			"origin":         origin,
			"dest":           dest,
			"make":           make_,
			"min_confidence": minConf,
			"sort":           sortCol,
		},
	}
	writeJSONCached(r.Context(), w, d.Redis, cacheKey, 5*time.Minute, http.StatusOK, resp)
}

// ── ArbitrageRouteStats ───────────────────────────────────────────────────────

// ArbitrageRouteStats handles GET /api/v1/arbitrage/routes
// Returns top 50 routes by avg_margin_eur, cached 1h.
func (d *Deps) ArbitrageRouteStats(w http.ResponseWriter, r *http.Request) {
	const cacheKey = "arbitrage:routes:top50"

	if cached, err := d.Redis.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.WriteHeader(http.StatusOK)
		w.Write(cached)
		return
	}

	rows, err := d.CH.Query(r.Context(),
		"SELECT route_key, origin_country, dest_country, make, model_family, fuel_type,"+
			" avg_margin_eur, avg_margin_pct, opportunity_count, avg_confidence, last_updated"+
			" FROM cardex.arbitrage_route_stats"+
			" ORDER BY avg_margin_eur DESC"+
			" LIMIT 50",
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	routes := make([]arbitrageRouteStats, 0, 50)
	for rows.Next() {
		var s arbitrageRouteStats
		var lastUpdated time.Time
		if err := rows.Scan(
			&s.RouteKey, &s.OriginCountry, &s.DestCountry,
			&s.Make, &s.ModelFamily, &s.FuelType,
			&s.AvgMarginEUR, &s.AvgMarginPct,
			&s.OpportunityCount, &s.AvgConfidence, &lastUpdated,
		); err != nil {
			continue
		}
		s.LastUpdated = lastUpdated.Format(time.RFC3339)
		routes = append(routes, s)
	}

	resp := map[string]any{"routes": routes, "count": len(routes)}
	writeJSONCached(r.Context(), w, d.Redis, cacheKey, time.Hour, http.StatusOK, resp)
}

// ── ArbitrageNLCBreakdown ─────────────────────────────────────────────────────

// ArbitrageNLCBreakdown handles GET /api/v1/arbitrage/nlc/{ticker}/{origin}/{dest}
// ticker format: "BMW_3-Series_2020_Gasoline" (make_model_year_fuel)
func (d *Deps) ArbitrageNLCBreakdown(w http.ResponseWriter, r *http.Request) {
	ticker := r.PathValue("ticker")
	origin := strings.ToUpper(strings.TrimSpace(r.PathValue("origin")))
	dest := strings.ToUpper(strings.TrimSpace(r.PathValue("dest")))

	if ticker == "" || len(origin) != 2 || len(dest) != 2 {
		writeError(w, http.StatusBadRequest, "invalid_params",
			"ticker, origin, and dest are required; origin/dest must be 2-char country codes")
		return
	}
	if !isAlpha(origin) || !isAlpha(dest) {
		writeError(w, http.StatusBadRequest, "invalid_params", "origin and dest must contain only letters")
		return
	}

	// Parse ticker: MAKE_MODEL_YEAR_FUEL — model may contain hyphens and underscores
	// Convention: last segment = fuel, second-to-last = year (4-digit), rest = make_model
	parts := strings.Split(ticker, "_")
	if len(parts) < 4 {
		writeError(w, http.StatusBadRequest, "invalid_ticker",
			"ticker must be in format MAKE_MODEL_YEAR_FUEL (e.g. BMW_3-Series_2020_Gasoline)")
		return
	}
	make_ := parts[0]
	fuelType := parts[len(parts)-1]
	yearStr := parts[len(parts)-2]
	model := strings.Join(parts[1:len(parts)-2], "_")

	year, err := strconv.Atoi(yearStr)
	if err != nil || year < 1980 || year > 2030 {
		writeError(w, http.StatusBadRequest, "invalid_ticker", "year in ticker is invalid")
		return
	}

	// Fetch price medians for origin and dest from ClickHouse price index
	type priceRow struct {
		MedianEUR float64
		Volume    uint32
	}
	fetchMedian := func(country string) (priceRow, error) {
		row := d.CH.QueryRow(r.Context(),
			"SELECT median_eur, volume"+
				" FROM cardex.price_index"+
				" WHERE make = ? AND model = ? AND year = ? AND country = ?"+
				" ORDER BY index_date DESC LIMIT 1",
			make_, model, uint16(year), country,
		)
		var pr priceRow
		if scanErr := row.Scan(&pr.MedianEUR, &pr.Volume); scanErr != nil {
			return pr, fmt.Errorf("no price index data for %s %s %d in %s", make_, model, year, country)
		}
		return pr, nil
	}

	// Fetch best available CO2 value from inventory
	fetchCO2 := func() int {
		var co2 uint16
		_ = d.CH.QueryRow(r.Context(),
			"SELECT co2_gkm FROM cardex.vehicle_inventory"+
				" WHERE make = ? AND model = ? AND year = ? AND co2_gkm > 0"+
				" ORDER BY last_updated_at DESC LIMIT 1",
			make_, model, uint16(year),
		).Scan(&co2)
		return int(co2)
	}

	originRow, err := fetchMedian(origin)
	if err != nil {
		writeError(w, http.StatusNotFound, "no_origin_data", err.Error())
		return
	}
	destRow, err := fetchMedian(dest)
	if err != nil {
		writeError(w, http.StatusNotFound, "no_dest_data", err.Error())
		return
	}

	co2 := fetchCO2()
	ageYears := time.Now().Year() - year
	ageMonths := ageYears * 12

	nlcInput := nlc.NLCInput{
		GrossPhysicalCostEUR: originRow.MedianEUR,
		OriginCountry:        origin,
		TargetCountry:        dest,
		CO2GKM:               co2,
		VehicleAgeYears:      ageYears,
		VehicleAgeMonths:     ageMonths,
	}

	nlcResult, err := d.NLCCalc.Compute(r.Context(), nlcInput)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "nlc_error", err.Error())
		return
	}

	totalNLC := nlcResult.LogisticsCostEUR + nlcResult.TaxAmountEUR
	grossMargin := destRow.MedianEUR - originRow.MedianEUR - totalNLC
	var marginPct float64
	if originRow.MedianEUR > 0 {
		marginPct = grossMargin / originRow.MedianEUR * 100
	}

	taxType, taxRatePct := taxTypeForRoute(dest, co2)

	writeJSON(w, http.StatusOK, nlcBreakdownResponse{
		Ticker:          ticker,
		Origin:          origin,
		Dest:            dest,
		OriginMedianEUR: originRow.MedianEUR,
		DestMedianEUR:   destRow.MedianEUR,
		NLCBreakdown: nlcBreakdown{
			LogisticsEUR: nlcResult.LogisticsCostEUR,
			OriginTaxEUR: 0, // origin countries do not charge export tax in these routes
			DestTaxEUR:   nlcResult.TaxAmountEUR,
			TotalNLCEUR:  totalNLC,
			TaxType:      taxType,
			TaxRatePct:   taxRatePct,
			CO2GKM:       co2,
		},
		GrossMarginEUR: grossMargin,
		MarginPct:      marginPct,
		Recommendation: marginRecommendation(marginPct),
	})

	_ = fuelType // parsed for completeness; future NLC versions will use fuel type
}

// ── ArbitrageBookOpportunity ──────────────────────────────────────────────────

// ArbitrageBookOpportunity handles POST /api/v1/arbitrage/book/{opportunity_id}
// JWT required. Marks opportunity as BOOKED and records it in the entity's Redis portfolio.
func (d *Deps) ArbitrageBookOpportunity(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "authentication required")
		return
	}

	opportunityID := r.PathValue("opportunity_id")
	if opportunityID == "" {
		writeError(w, http.StatusBadRequest, "missing_id", "opportunity_id is required")
		return
	}
	// Validate: opportunity_id must be a safe identifier (hex chars and hyphens only)
	for _, c := range opportunityID {
		if !((c >= 'a' && c <= 'f') || (c >= '0' && c <= '9') || c == '-') {
			writeError(w, http.StatusBadRequest, "invalid_id", "invalid opportunity_id format")
			return
		}
	}

	// Verify the opportunity exists and is still ACTIVE
	var existingID string
	row := d.CH.QueryRow(r.Context(),
		"SELECT opportunity_id FROM cardex.arbitrage_opportunities"+
			" WHERE opportunity_id = ? AND status = 'ACTIVE'"+
			" ORDER BY scanned_at DESC LIMIT 1",
		opportunityID,
	)
	if err := row.Scan(&existingID); err != nil {
		writeError(w, http.StatusNotFound, "not_found", "opportunity not found or no longer active")
		return
	}

	// INSERT new row with status=BOOKED — ReplacingMergeTree(scanned_at) will keep this latest version
	if err := d.CH.Exec(r.Context(),
		"INSERT INTO cardex.arbitrage_opportunities (opportunity_id, status, scanned_at) VALUES (?, 'BOOKED', now())",
		opportunityID,
	); err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", "failed to book opportunity: "+err.Error())
		return
	}

	// Record in Redis sorted set (score = Unix timestamp) for fast portfolio retrieval
	portfolioKey := "arbitrage:booked:" + entityULID
	d.Redis.ZAdd(r.Context(), portfolioKey, redis.Z{
		Score:  float64(time.Now().Unix()),
		Member: opportunityID,
	})
	d.Redis.Expire(r.Context(), portfolioKey, 30*24*time.Hour)

	writeJSON(w, http.StatusOK, map[string]any{
		"opportunity_id": opportunityID,
		"status":         "BOOKED",
		"entity_ulid":    entityULID,
		"booked_at":      time.Now().UTC().Format(time.RFC3339),
	})
}

// ── ArbitrageBookedList ───────────────────────────────────────────────────────

// ArbitrageBookedList handles GET /api/v1/arbitrage/booked
// JWT required. Returns all booked opportunities for the authenticated entity.
func (d *Deps) ArbitrageBookedList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "authentication required")
		return
	}

	portfolioKey := "arbitrage:booked:" + entityULID

	// Retrieve opportunity IDs from Redis sorted set (newest first)
	ids, err := d.Redis.ZRevRange(r.Context(), portfolioKey, 0, -1).Result()
	if err != nil || len(ids) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"entity_ulid":   entityULID,
			"opportunities": []arbitrageOpportunity{},
			"count":         0,
		})
		return
	}

	// Build IN clause for ClickHouse query
	placeholders := make([]string, len(ids))
	args := make([]any, len(ids))
	for i, id := range ids {
		placeholders[i] = "?"
		args[i] = id
	}

	rows, err := d.CH.Query(r.Context(),
		"SELECT opportunity_id, scanned_at, opportunity_type, make, model, year, fuel_type,"+
			" origin_country, dest_country, origin_median_eur, dest_median_eur, nlc_estimate_eur,"+
			" gross_margin_eur, margin_pct, confidence_score, sample_size_origin, sample_size_dest,"+
			" co2_gkm, bpm_refund_eur, iedmt_eur, malus_eur, example_listing_url, status"+
			" FROM cardex.arbitrage_opportunities"+
			" WHERE opportunity_id IN ("+strings.Join(placeholders, ",")+")" +
			" ORDER BY scanned_at DESC",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	opportunities := make([]arbitrageOpportunity, 0, len(ids))
	for rows.Next() {
		var o arbitrageOpportunity
		var scannedAt time.Time
		if err := rows.Scan(
			&o.OpportunityID, &scannedAt, &o.OpportunityType,
			&o.Make, &o.Model, &o.Year, &o.FuelType,
			&o.OriginCountry, &o.DestCountry,
			&o.OriginMedianEUR, &o.DestMedianEUR, &o.NLCEstimateEUR,
			&o.GrossMarginEUR, &o.MarginPct, &o.ConfidenceScore,
			&o.SampleSizeOrigin, &o.SampleSizeDest,
			&o.CO2GKM, &o.BPMRefundEUR, &o.IEDMTEUR, &o.MalusEUR,
			&o.ExampleListingURL, &o.Status,
		); err != nil {
			continue
		}
		o.ScannedAt = scannedAt.Format(time.RFC3339)
		opportunities = append(opportunities, o)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_ulid":   entityULID,
		"opportunities": opportunities,
		"count":         len(opportunities),
	})
}

// ── Internal helpers ──────────────────────────────────────────────────────────

// writeJSONCached marshals resp, stores in Redis with the given TTL, and writes to w.
func writeJSONCached(ctx context.Context, w http.ResponseWriter, rdb *redis.Client, key string, ttl time.Duration, status int, resp any) {
	b, err := json.Marshal(resp)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "json_error", err.Error())
		return
	}
	rdb.Set(ctx, key, b, ttl)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.WriteHeader(status)
	w.Write(b)
}

// taxTypeForRoute returns the destination registration tax type and rate for display.
func taxTypeForRoute(dest string, co2 int) (string, float64) {
	switch dest {
	case "ES":
		switch {
		case co2 > 200:
			return "IEDMT", 14.75
		case co2 > 160:
			return "IEDMT", 9.75
		case co2 > 120:
			return "IEDMT", 4.75
		default:
			return "IEDMT", 0
		}
	case "FR":
		if co2 > 117 {
			return "Malus", 0 // variable amount — computed by NLC calculator
		}
		return "None", 0
	case "NL":
		if co2 > 0 {
			return "RestBPM", 0 // variable amount — computed by NLC calculator
		}
		return "None", 0
	default:
		return "None", 0
	}
}

// marginRecommendation returns a qualitative rating based on the gross margin percentage.
func marginRecommendation(marginPct float64) string {
	switch {
	case marginPct >= 15:
		return "STRONG_BUY"
	case marginPct >= 8:
		return "VIABLE"
	case marginPct >= 3:
		return "MARGINAL"
	default:
		return "AVOID"
	}
}

// isAlpha returns true if every rune in s is an ASCII letter and s is non-empty.
func isAlpha(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) {
			return false
		}
	}
	return true
}

// isAlphaUnderscore returns true if s contains only ASCII letters, digits, or underscores.
func isAlphaUnderscore(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_') {
			return false
		}
	}
	return true
}

// parseFloat parses a float64 from a string, returning def on failure.
func parseFloat(s string, def float64) float64 {
	if s == "" {
		return def
	}
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return def
	}
	return v
}
