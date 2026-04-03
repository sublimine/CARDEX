package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/cardex/api/internal/middleware"
)

// ── Market Days Supply ────────────────────────────────────────────────────────

type mdsRow struct {
	Make            string  `json:"make"`
	Model           string  `json:"model"`
	Country         string  `json:"country"`
	ActiveListings  int64   `json:"active_listings"`
	DailyAbsorption float64 `json:"daily_absorption"`
	MDSDays         float64 `json:"mds_days"`
	DemandRating    string  `json:"demand_rating"`
}

// MarketDaysSupply handles GET /api/v1/analytics/mds
func (d *Deps) MarketDaysSupply(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	q := r.URL.Query()
	makeFilter := q.Get("make")
	modelFilter := q.Get("model")
	countryFilter := q.Get("country")

	var where []string
	var args []any

	if makeFilter != "" {
		where = append(where, "make = ?")
		args = append(args, makeFilter)
	}
	if modelFilter != "" {
		where = append(where, "model = ?")
		args = append(args, modelFilter)
	}
	if countryFilter != "" {
		where = append(where, "origin_country = ?")
		args = append(args, countryFilter)
	}

	baseWhere := ""
	if len(where) > 0 {
		baseWhere = " AND " + strings.Join(where, " AND ")
	}

	query := fmt.Sprintf(`
SELECT
    make,
    model,
    origin_country,
    countIf(lifecycle_status = 'ACTIVE' AND last_updated_at >= now() - INTERVAL 7 DAY)           AS active_count,
    countIf(lifecycle_status IN ('EXPIRED','SOLD') AND last_updated_at >= now() - INTERVAL 30 DAY) / 30.0 AS daily_absorption
FROM cardex.vehicle_inventory
WHERE 1=1 %s
GROUP BY make, model, origin_country
ORDER BY active_count DESC
LIMIT 50`, baseWhere)

	rows, err := d.CH.Query(ctx, query, args...)
	if err != nil {
		slog.Error("intelligence.mds: ch query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "ch_unavailable", "analytics service temporarily unavailable")
		return
	}
	defer rows.Close()

	var results []mdsRow
	for rows.Next() {
		var row mdsRow
		if err := rows.Scan(&row.Make, &row.Model, &row.Country, &row.ActiveListings, &row.DailyAbsorption); err != nil {
			slog.Warn("intelligence.mds: row scan", "error", err)
			continue
		}
		absorption := math.Max(row.DailyAbsorption, 0.1)
		row.MDSDays = math.Round(float64(row.ActiveListings)/absorption*10) / 10
		switch {
		case row.MDSDays < 20:
			row.DemandRating = "HIGH"
		case row.MDSDays < 45:
			row.DemandRating = "MEDIUM"
		default:
			row.DemandRating = "LOW"
		}
		results = append(results, row)
	}
	if results == nil {
		results = []mdsRow{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"results": results})
}

// ── Turn Time Prediction ──────────────────────────────────────────────────────

type turnTimePredictionResponse struct {
	Make              string  `json:"make"`
	Model             string  `json:"model"`
	Country           string  `json:"country"`
	Year              int     `json:"year"`
	MedianPriceEUR    float64 `json:"median_price_eur"`
	MedianDOMDays     float64 `json:"median_dom_days"`
	PricePremiumPct   float64 `json:"price_premium_pct"`
	PredictedTurnDays float64 `json:"predicted_turn_days"`
	Confidence        string  `json:"confidence"`
}

// TurnTimePrediction handles GET /api/v1/analytics/turn-time
func (d *Deps) TurnTimePrediction(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	q := r.URL.Query()
	makeParam := q.Get("make")
	modelParam := q.Get("model")
	countryParam := q.Get("country")
	priceStr := q.Get("price_eur")
	yearStr := q.Get("year")

	priceEUR, _ := strconv.ParseFloat(priceStr, 64)
	year, _ := strconv.Atoi(yearStr)

	// Query median price (avg gross_physical_cost_eur of active listings)
	var medianPrice float64
	var sampleCount int64
	priceQuery := `
SELECT avg(gross_physical_cost_eur), count()
FROM cardex.vehicle_inventory
WHERE lifecycle_status = 'ACTIVE'
  AND make = ? AND model = ? AND origin_country = ? AND year = ?`
	priceRow := d.CH.QueryRow(ctx, priceQuery, makeParam, modelParam, countryParam, year)
	if err := priceRow.Scan(&medianPrice, &sampleCount); err != nil {
		slog.Warn("intelligence.turn-time: price scan", "error", err)
	}

	// Query median DOM (avg days_on_market for sold vehicles, last 90 days)
	var medianDOM float64
	domQuery := `
SELECT avg(days_on_market)
FROM cardex.vehicle_inventory
WHERE sold_at IS NOT NULL
  AND sold_at >= now() - INTERVAL 90 DAY
  AND make = ? AND model = ? AND origin_country = ? AND year = ?`
	domRow := d.CH.QueryRow(ctx, domQuery, makeParam, modelParam, countryParam, year)
	if err := domRow.Scan(&medianDOM); err != nil {
		slog.Warn("intelligence.turn-time: dom scan", "error", err)
		medianDOM = 45 // sensible fallback
	}
	if medianDOM == 0 {
		medianDOM = 45
	}

	var pricePremiumPct float64
	if medianPrice > 0 {
		pricePremiumPct = (priceEUR - medianPrice) / medianPrice * 100
	}

	predictedDays := medianDOM * (1 + pricePremiumPct*0.015)
	predictedDays = math.Max(5, math.Min(365, predictedDays))
	predictedDays = math.Round(predictedDays*10) / 10

	confidence := "LOW"
	switch {
	case sampleCount > 30:
		confidence = "HIGH"
	case sampleCount > 10:
		confidence = "MEDIUM"
	}

	writeJSON(w, http.StatusOK, turnTimePredictionResponse{
		Make:              makeParam,
		Model:             modelParam,
		Country:           countryParam,
		Year:              year,
		MedianPriceEUR:    math.Round(medianPrice*100) / 100,
		MedianDOMDays:     math.Round(medianDOM*10) / 10,
		PricePremiumPct:   math.Round(pricePremiumPct*100) / 100,
		PredictedTurnDays: predictedDays,
		Confidence:        confidence,
	})
}

// ── Market Check (Chrome Extension) ──────────────────────────────────────────

type marketCheckResponse struct {
	MarketPosition    string  `json:"market_position"`
	MarketPercentile  float64 `json:"market_percentile"`
	MedianPriceEUR    float64 `json:"median_price_eur"`
	P25PriceEUR       float64 `json:"p25_price_eur"`
	P75PriceEUR       float64 `json:"p75_price_eur"`
	MDSDays           float64 `json:"mds_days"`
	PredictedTurnDays float64 `json:"predicted_turn_days"`
	ArbitrageFlag     bool    `json:"arbitrage_flag"`
	CheapestCountry   string  `json:"cheapest_country,omitempty"`
	PriceDeltaEUR     float64 `json:"price_delta_eur,omitempty"`
}

// MarketCheck handles GET /api/v1/ext/market-check
func (d *Deps) MarketCheck(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	q := r.URL.Query()
	makeParam := q.Get("make")
	modelParam := q.Get("model")
	yearStr := q.Get("year")
	priceStr := q.Get("price_eur")
	countryParam := q.Get("country")

	// Validate required params
	if makeParam == "" || modelParam == "" || yearStr == "" || priceStr == "" || countryParam == "" {
		writeError(w, http.StatusBadRequest, "missing_params", "make, model, year, price_eur, country are required")
		return
	}

	year, err := strconv.Atoi(yearStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_year", "year must be an integer")
		return
	}
	priceEUR, err := strconv.ParseFloat(priceStr, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_price", "price_eur must be a number")
		return
	}

	var resp marketCheckResponse

	// --- Price percentiles ---
	pctQuery := `
SELECT
    quantile(0.25)(gross_physical_cost_eur) AS p25,
    quantile(0.50)(gross_physical_cost_eur) AS p50,
    quantile(0.75)(gross_physical_cost_eur) AS p75,
    countIf(gross_physical_cost_eur < ?) AS below_count,
    count() AS total_count
FROM cardex.vehicle_inventory
WHERE lifecycle_status = 'ACTIVE'
  AND make = ? AND model = ? AND year = ? AND origin_country = ?`

	pctRow := d.CH.QueryRow(ctx, pctQuery, priceEUR, makeParam, modelParam, year, countryParam)
	var belowCount, totalCount int64
	if err := pctRow.Scan(&resp.P25PriceEUR, &resp.MedianPriceEUR, &resp.P75PriceEUR, &belowCount, &totalCount); err != nil {
		slog.Warn("intelligence.market-check: percentile scan", "error", err)
	}

	if totalCount > 0 {
		resp.MarketPercentile = math.Round(float64(belowCount)/float64(totalCount)*100*10) / 10
	}
	switch {
	case priceEUR < resp.P25PriceEUR:
		resp.MarketPosition = "CHEAP"
	case priceEUR > resp.P75PriceEUR:
		resp.MarketPosition = "EXPENSIVE"
	default:
		resp.MarketPosition = "FAIR"
	}

	// --- MDS ---
	mdsQuery := `
SELECT
    countIf(lifecycle_status = 'ACTIVE' AND last_updated_at >= now() - INTERVAL 7 DAY),
    countIf(lifecycle_status IN ('EXPIRED','SOLD') AND last_updated_at >= now() - INTERVAL 30 DAY) / 30.0
FROM cardex.vehicle_inventory
WHERE make = ? AND model = ? AND origin_country = ?`
	mdsRow := d.CH.QueryRow(ctx, mdsQuery, makeParam, modelParam, countryParam)
	var activeCount int64
	var dailyAbsorption float64
	if err := mdsRow.Scan(&activeCount, &dailyAbsorption); err != nil {
		slog.Warn("intelligence.market-check: mds scan", "error", err)
	}
	absorption := math.Max(dailyAbsorption, 0.1)
	resp.MDSDays = math.Round(float64(activeCount)/absorption*10) / 10

	// --- Predicted turn days ---
	var medianDOM float64
	domQuery := `
SELECT avg(days_on_market)
FROM cardex.vehicle_inventory
WHERE sold_at IS NOT NULL
  AND sold_at >= now() - INTERVAL 90 DAY
  AND make = ? AND model = ? AND origin_country = ? AND year = ?`
	domRow := d.CH.QueryRow(ctx, domQuery, makeParam, modelParam, countryParam, year)
	if err := domRow.Scan(&medianDOM); err != nil || medianDOM == 0 {
		medianDOM = 45
	}
	var pricePremiumPct float64
	if resp.MedianPriceEUR > 0 {
		pricePremiumPct = (priceEUR - resp.MedianPriceEUR) / resp.MedianPriceEUR * 100
	}
	predicted := medianDOM * (1 + pricePremiumPct*0.015)
	resp.PredictedTurnDays = math.Round(math.Max(5, math.Min(365, predicted))*10) / 10

	// --- Arbitrage flag ---
	arbQuery := `
SELECT
    origin_country,
    avg(gross_physical_cost_eur) AS avg_price
FROM cardex.vehicle_inventory
WHERE lifecycle_status = 'ACTIVE'
  AND make = ? AND model = ? AND year = ?
  AND origin_country != ?
GROUP BY origin_country
ORDER BY avg_price ASC
LIMIT 1`
	arbRow := d.CH.QueryRow(ctx, arbQuery, makeParam, modelParam, year, countryParam)
	var cheapestCountry string
	var cheapestPrice float64
	if err := arbRow.Scan(&cheapestCountry, &cheapestPrice); err == nil {
		if cheapestPrice > 0 && (priceEUR-cheapestPrice)/cheapestPrice*100 > 15 {
			resp.ArbitrageFlag = true
			resp.CheapestCountry = cheapestCountry
			resp.PriceDeltaEUR = math.Round((priceEUR-cheapestPrice)*100) / 100
		}
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── Optimal Pricing ───────────────────────────────────────────────────────────

type pricingOption struct {
	Label            string  `json:"label"`
	PriceEUR         float64 `json:"price_eur"`
	EstimatedDOMDays int     `json:"estimated_dom_days"`
	MarginEUR        float64 `json:"margin_eur"`
	MarginPct        float64 `json:"margin_pct"`
	Constrained      bool    `json:"constrained"`
}

type optimalPriceResponse struct {
	TotalCostEUR float64         `json:"total_cost_eur"`
	FloorPriceEUR float64        `json:"floor_price_eur"`
	Options      []pricingOption `json:"options"`
	Market       struct {
		Median      float64 `json:"median"`
		P25         float64 `json:"p25"`
		P75         float64 `json:"p75"`
		AvgDOM      float64 `json:"avg_dom"`
		SampleCount int64   `json:"sample_count"`
	} `json:"market"`
}

// OptimalPrice handles GET /api/v1/dealer/pricing/{ulid}/optimal
func (d *Deps) OptimalPrice(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	vehicleULID := r.PathValue("ulid")
	entityULID := middleware.GetEntityULID(r.Context())

	if vehicleULID == "" || entityULID == "" {
		writeError(w, http.StatusBadRequest, "missing_params", "ulid and entity context required")
		return
	}

	// Fetch CRM vehicle with cost fields (multi-tenant check)
	var (
		makeVal, modelVal, countryVal string
		vehicleYear                   int
		purchasePrice, reconCost, transportCost,
		homologationCost, marketingCost, financingCost, otherCost float64
	)
	pgQuery := `
SELECT
    COALESCE(make,''), COALESCE(model,''), COALESCE(year,0), COALESCE(country_code,''),
    COALESCE(purchase_price_eur,0), COALESCE(recon_cost_eur,0), COALESCE(transport_cost_eur,0),
    COALESCE(homologation_cost_eur,0), COALESCE(marketing_cost_eur,0),
    COALESCE(financing_cost_eur,0), COALESCE(other_cost_eur,0)
FROM crm_vehicles
WHERE crm_vehicle_ulid = $1 AND entity_ulid = $2`

	err := d.DB.QueryRow(ctx, pgQuery, vehicleULID, entityULID).Scan(
		&makeVal, &modelVal, &vehicleYear, &countryVal,
		&purchasePrice, &reconCost, &transportCost,
		&homologationCost, &marketingCost, &financingCost, &otherCost,
	)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "vehicle not found")
		return
	}

	totalCost := purchasePrice + reconCost + transportCost + homologationCost + marketingCost + financingCost + otherCost
	floorPrice := totalCost * 1.05

	// Query ClickHouse for market stats
	var resp optimalPriceResponse
	resp.TotalCostEUR = math.Round(totalCost*100) / 100
	resp.FloorPriceEUR = math.Round(floorPrice*100) / 100

	chQuery := `
SELECT
    quantile(0.25)(gross_physical_cost_eur) AS p25,
    quantile(0.50)(gross_physical_cost_eur) AS median,
    quantile(0.75)(gross_physical_cost_eur) AS p75,
    avg(days_on_market) AS avg_dom,
    count() AS sample_count
FROM cardex.vehicle_inventory
WHERE lifecycle_status = 'ACTIVE'
  AND make = ? AND model = ? AND year = ? AND origin_country = ?`

	chRow := d.CH.QueryRow(ctx, chQuery, makeVal, modelVal, vehicleYear, countryVal)
	if err := chRow.Scan(&resp.Market.P25, &resp.Market.Median, &resp.Market.P75, &resp.Market.AvgDOM, &resp.Market.SampleCount); err != nil {
		slog.Warn("intelligence.optimal-price: market scan", "error", err)
	}

	makeOption := func(label string, rawPrice float64, estDOM int) pricingOption {
		price := math.Round(rawPrice*100) / 100
		constrained := false
		if price < floorPrice {
			price = math.Round(floorPrice*100) / 100
			constrained = true
		}
		marginEUR := price - totalCost
		var marginPct float64
		if totalCost > 0 {
			marginPct = math.Round(marginEUR/totalCost*10000) / 100
		}
		return pricingOption{
			Label:            label,
			PriceEUR:         price,
			EstimatedDOMDays: estDOM,
			MarginEUR:        math.Round(marginEUR*100) / 100,
			MarginPct:        marginPct,
			Constrained:      constrained,
		}
	}

	resp.Options = []pricingOption{
		makeOption("DOM-30 (market median)", resp.Market.Median, 30),
		makeOption("DOM-15 (aggressive)", resp.Market.P25*0.98, 15),
		makeOption("DOM-60 (premium)", resp.Market.P75*1.02, 60),
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── AI Description Generator ──────────────────────────────────────────────────

type generateDescriptionRequest struct {
	Make         string   `json:"make"`
	Model        string   `json:"model"`
	Year         int      `json:"year"`
	FuelType     string   `json:"fuel_type"`
	Transmission string   `json:"transmission"`
	MileageKM    int      `json:"mileage_km"`
	Color        string   `json:"color"`
	PowerKW      int      `json:"power_kw"`
	Extras       []string `json:"extras"`
	Language     string   `json:"language"`
}

type generateDescriptionResponse struct {
	Description string `json:"description"`
	Language    string `json:"language"`
	GeneratedAt string `json:"generated_at"`
}

// GenerateDescription handles POST /api/v1/dealer/inventory/generate-description
func (d *Deps) GenerateDescription(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req generateDescriptionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", "invalid JSON body")
		return
	}

	if req.Language == "" {
		req.Language = "en"
	}
	validLangs := map[string]bool{"es": true, "fr": true, "de": true, "nl": true, "en": true}
	if !validLangs[req.Language] {
		req.Language = "en"
	}

	extras := strings.Join(req.Extras, ", ")
	if extras == "" {
		extras = "N/A"
	}

	prompt := fmt.Sprintf(
		"Genera un anuncio de venta atractivo y profesional en %s para este vehículo: %d %s %s, combustible: %s, transmisión: %s, kilómetros: %d km, color: %s, potencia: %d kW, extras: %s. Máximo 300 palabras. Sin precios. Tono profesional pero accesible.",
		req.Language, req.Year, req.Make, req.Model,
		req.FuelType, req.Transmission, req.MileageKM,
		req.Color, req.PowerKW, extras,
	)

	description := callAnthropicOrTemplate(ctx, prompt, req)

	writeJSON(w, http.StatusOK, generateDescriptionResponse{
		Description: description,
		Language:    req.Language,
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
	})
}

// callAnthropicOrTemplate calls the Anthropic API; on any failure returns a template description.
func callAnthropicOrTemplate(ctx context.Context, prompt string, req generateDescriptionRequest) string {
	apiKey := os.Getenv("ANTHROPIC_API_KEY")
	if apiKey == "" {
		return buildTemplateDescription(req)
	}

	body := map[string]any{
		"model":      "claude-haiku-4-5-20251001",
		"max_tokens": 512,
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
	}
	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return buildTemplateDescription(req)
	}

	httpClient := &http.Client{Timeout: 30 * time.Second}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		"https://api.anthropic.com/v1/messages", bytes.NewReader(bodyBytes))
	if err != nil {
		return buildTemplateDescription(req)
	}
	httpReq.Header.Set("x-api-key", apiKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")
	httpReq.Header.Set("content-type", "application/json")

	resp, err := httpClient.Do(httpReq)
	if err != nil {
		slog.Warn("intelligence.generate-description: anthropic call failed", "error", err)
		return buildTemplateDescription(req)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Warn("intelligence.generate-description: anthropic status", "status", resp.StatusCode)
		return buildTemplateDescription(req)
	}

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return buildTemplateDescription(req)
	}

	var anthropicResp struct {
		Content []struct {
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := json.Unmarshal(respBytes, &anthropicResp); err != nil || len(anthropicResp.Content) == 0 {
		return buildTemplateDescription(req)
	}
	return anthropicResp.Content[0].Text
}

func buildTemplateDescription(req generateDescriptionRequest) string {
	extras := ""
	if len(req.Extras) > 0 {
		extras = fmt.Sprintf(" Equipado con: %s.", strings.Join(req.Extras, ", "))
	}
	return fmt.Sprintf(
		"%d %s %s — %s, %s, %d km, %d kW.%s Vehículo en excelente estado, revisado y listo para su nueva vida. Contacta con nosotros para más información.",
		req.Year, req.Make, req.Model,
		req.FuelType, req.Transmission, req.MileageKM, req.PowerKW,
		extras,
	)
}
