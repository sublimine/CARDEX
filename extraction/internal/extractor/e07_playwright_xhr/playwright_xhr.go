// Package e07_playwright_xhr implements extraction strategy E07 — Playwright XHR.
//
// # Strategy
//
// Some dealer sites are full SPAs (React/Vue/Angular) that render their
// inventory entirely client-side by fetching data from a backend JSON API.
// Standard HTML extraction (E01-E06) yields empty pages. E07 intercepts the
// XHR/fetch requests the SPA makes during page load, captures the JSON
// responses, and extracts vehicle data directly from them — without needing
// to reverse-engineer the API endpoint.
//
// # XHRInterceptor interface
//
// E07 depends on the XHRInterceptor interface defined in this package.
// The real implementation is provided by the discovery/internal/browser package
// (PlaywrightBrowser.InterceptXHR). Since that package is internal to the
// discovery module, callers must inject a compatible implementation via
// NewWithInterceptor. The default New() constructor uses a no-op stub that
// logs a warning — useful in deployments without Playwright.
//
// # JSON heuristic mapping
//
// XHR response bodies are parsed with a heuristic that looks for vehicle lists
// in common wrapper keys: vehicles, inventory, results, items, listings, data.
// Field mapping uses the same flexible mapper as E05.
//
// # Inventory page probing
//
// E07 navigates to several candidate inventory paths (/, /inventory, /vehicles,
// /cars, /used-cars, /stock) and collects all matching XHR responses.
//
// # Applicability
//
// Returns true for dealers with UNKNOWN/empty PlatformType or when the
// extraction hint "spa_detected" is present. Also always returns true if the
// dealer has no structured data signals (no schema_org, no cms, no dms).
//
// Priority: 700 (last resort before manual review).
package e07_playwright_xhr

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E07"
	strategyName = "Playwright XHR Interception"
	maxXHRItems  = 500
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// XHRCapture holds the captured request/response from a single XHR call.
type XHRCapture struct {
	RequestURL     string
	ResponseBody   []byte
	ResponseStatus int
}

// XHRInterceptor navigates to a URL using a headless browser, captures all
// network responses whose URL matches the filter, and returns them.
// The real implementation is PlaywrightBrowser.InterceptXHR from the
// discovery/internal/browser package.
type XHRInterceptor interface {
	InterceptXHR(ctx context.Context, url string, filter func(string) bool) ([]*XHRCapture, error)
}

// xhrFilter returns true for URLs likely to carry vehicle inventory JSON.
func xhrFilter(url string) bool {
	lower := strings.ToLower(url)
	for _, kw := range []string{
		"/api/", "/vehicles", "/inventory", "/listings", "/cars", "/stock",
		"format=json", "type=vehicle", "/catalog",
	} {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// inventoryPaths are the SPA entry pages probed for XHR activity.
var inventoryPaths = []string{
	"/inventory",
	"/vehicles",
	"/cars",
	"/used-cars",
	"/stock",
	"/",
}

// noOpInterceptor is the default stub used when Playwright is not configured.
type noOpInterceptor struct {
	log *slog.Logger
}

func (n *noOpInterceptor) InterceptXHR(_ context.Context, url string, _ func(string) bool) ([]*XHRCapture, error) {
	n.log.Warn("E07: Playwright not configured — XHR interception is a no-op",
		"url", url,
		"hint", "inject a real XHRInterceptor via NewWithInterceptor to enable SPA extraction",
	)
	return nil, nil
}

// PlaywrightXHR is the E07 extraction strategy.
type PlaywrightXHR struct {
	interceptor XHRInterceptor
	client      *http.Client // used for optional HEAD probe to pick best inventory path
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a PlaywrightXHR strategy with a no-op XHR interceptor.
// Inject a real interceptor via NewWithInterceptor for production use.
func New() *PlaywrightXHR {
	log := slog.Default().With("strategy", strategyID)
	return &PlaywrightXHR{
		interceptor: &noOpInterceptor{log: log},
		client:      &http.Client{Timeout: 10 * time.Second},
		rateLimitMs: 1000,
		log:         log,
	}
}

// NewWithInterceptor constructs a PlaywrightXHR strategy with the given XHR
// interceptor. Use this to inject the real Playwright browser implementation.
func NewWithInterceptor(interceptor XHRInterceptor, rateLimitMs int) *PlaywrightXHR {
	return &PlaywrightXHR{
		interceptor: interceptor,
		client:      &http.Client{Timeout: 10 * time.Second},
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

func (e *PlaywrightXHR) ID() string    { return strategyID }
func (e *PlaywrightXHR) Name() string  { return strategyName }
func (e *PlaywrightXHR) Priority() int { return pipeline.PriorityE07 }

// Applicable returns true for dealers without strong structured-data signals
// (no DMS, no known CMS) or when spa_detected hint is present.
func (e *PlaywrightXHR) Applicable(dealer pipeline.Dealer) bool {
	for _, hint := range dealer.ExtractionHints {
		if hint == "spa_detected" {
			return true
		}
	}
	// Apply if no DMS and no CMS signals (pure unknown/native site).
	if dealer.DMSProvider != "" {
		return false
	}
	cms := strings.ToLower(dealer.CMSDetected + dealer.PlatformType)
	if strings.Contains(cms, "wordpress") || strings.Contains(cms, "joomla") ||
		strings.Contains(cms, "shopify") || strings.Contains(cms, "dms") {
		return false
	}
	return true
}

// Extract navigates to each inventory path, intercepts XHR responses, and
// parses vehicle JSON from the captured responses.
func (e *PlaywrightXHR) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	seenVehicles := map[string]bool{}

	for i, path := range inventoryPaths {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			sleep := e.rateLimitMs
			if sleep <= 0 {
				sleep = 50
			}
			select {
			case <-ctx.Done():
				return result, nil
			case <-time.After(time.Duration(sleep) * time.Millisecond):
			}
		}

		pageURL := baseURL + path
		captures, err := e.interceptor.InterceptXHR(ctx, pageURL, xhrFilter)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "XHR_ERROR",
				Message: err.Error(),
				URL:     pageURL,
			})
			continue
		}
		if len(captures) == 0 {
			continue
		}

		for _, cap := range captures {
			if cap.ResponseStatus != http.StatusOK {
				continue
			}
			vehicles := parseXHRBody(cap.ResponseBody)
			for _, v := range vehicles {
				// Do NOT set SourceURL to cap.RequestURL — multiple vehicles
				// share the same API endpoint URL, which would collapse them
				// to a single dedup key.  SourceURL stays as the vehicle's
				// own detail-page URL (from the JSON) or empty.
				key := vehicleKey(v)
				if !seenVehicles[key] {
					seenVehicles[key] = true
					result.Vehicles = append(result.Vehicles, v)
					if len(result.Vehicles) >= maxXHRItems {
						break
					}
				}
			}
		}

		if len(result.Vehicles) > 0 {
			result.SourceURL = pageURL
			result.SourceCount = len(captures)
			break
		}
	}

	return result, nil
}

// parseXHRBody attempts to extract vehicle records from a raw XHR response body.
// Handles both root-array and root-object with common array wrappers.
func parseXHRBody(body []byte) []*pipeline.VehicleRaw {
	if len(body) == 0 {
		return nil
	}

	// Try root array.
	var arr []json.RawMessage
	if err := json.Unmarshal(body, &arr); err == nil {
		return mapXHRArray(arr)
	}

	// Try root object with common inventory keys.
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(body, &obj); err != nil {
		return nil // not valid JSON
	}

	for _, key := range []string{"vehicles", "inventory", "results", "items", "listings", "data", "records", "cars"} {
		if raw, ok := obj[key]; ok {
			var arr []json.RawMessage
			if err := json.Unmarshal(raw, &arr); err == nil && len(arr) > 0 {
				return mapXHRArray(arr)
			}
		}
	}
	return nil
}

// mapXHRArray maps a JSON array to VehicleRaw records using flexible field mapping.
func mapXHRArray(items []json.RawMessage) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw
	for _, raw := range items {
		var m map[string]json.RawMessage
		if err := json.Unmarshal(raw, &m); err != nil {
			continue
		}
		if v := extractFromXHRMap(m); v != nil {
			vehicles = append(vehicles, v)
		}
	}
	return vehicles
}

// extractFromXHRMap maps a flat JSON object (from XHR response) to a VehicleRaw.
// Uses generous field name aliases to handle SPA-specific field naming conventions.
func extractFromXHRMap(m map[string]json.RawMessage) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{}

	getString := func(keys ...string) string {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var s string
				if json.Unmarshal(raw, &s) == nil && s != "" {
					return s
				}
			}
		}
		return ""
	}

	getFloat := func(keys ...string) float64 {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var f float64
				if json.Unmarshal(raw, &f) == nil && f > 0 {
					return f
				}
				var s string
				if json.Unmarshal(raw, &s) == nil {
					if f2, err := strconv.ParseFloat(strings.TrimSpace(s), 64); err == nil && f2 > 0 {
						return f2
					}
				}
			}
		}
		return 0
	}

	getInt := func(keys ...string) int {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var n int
				if json.Unmarshal(raw, &n) == nil && n > 0 {
					return n
				}
				var f float64
				if json.Unmarshal(raw, &f) == nil && f > 0 {
					return int(f)
				}
			}
		}
		return 0
	}

	// VIN.
	if vin := normalize.NormalizeVIN(getString("vin", "VIN", "vehicleVin", "vehicle_vin", "Vin")); vin != "" {
		v.VIN = &vin
	}

	// Make.
	if mk := getString("make", "Make", "brand", "Brand", "manufacturer", "marque", "vehicleMake"); mk != "" {
		mk = normalize.NormalizeMake(mk)
		v.Make = &mk
	}

	// Model.
	if model := getString("model", "Model", "modelName", "vehicleModel", "model_name"); model != "" {
		v.Model = &model
	}

	// Year.
	if yr := getInt("year", "Year", "modelYear", "vehicleYear", "yearOfManufacture", "annee"); yr > 1900 && yr < 2100 {
		v.Year = &yr
	}

	// Mileage.
	if km := getInt("mileage", "Mileage", "odometer", "km", "kilometers", "kilometres", "vehicleMileage"); km > 0 {
		v.Mileage = &km
	}

	// Price.
	if p := getFloat("price", "Price", "salePrice", "askingPrice", "listPrice", "retail_price", "prix"); p > 0 {
		v.PriceGross = &p
	}

	// Color.
	if col := getString("color", "Color", "colour", "Farbe", "couleur", "exteriorColor", "exterior_color"); col != "" {
		v.Color = &col
	}

	// Fuel type.
	if fuel := normalize.NormalizeFuelType(getString("fuel", "fuelType", "FuelType", "propulsion", "carburant")); fuel != "" {
		v.FuelType = &fuel
	}

	// Transmission.
	if tx := normalize.NormalizeTransmission(getString("transmission", "Transmission", "gearbox", "boite")); tx != "" {
		v.Transmission = &tx
	}

	// SourceURL.
	if url := getString("url", "URL", "link", "detailUrl", "detail_url", "vehicleUrl", "permalink"); url != "" {
		v.SourceURL = url
	}

	// SourceListingID.
	if id := getString("id", "Id", "listingId", "vehicleId", "stockNumber", "stock_number"); id != "" {
		v.SourceListingID = id
	}

	if v.Make == nil && v.VIN == nil {
		return nil
	}
	return v
}

// vehicleKey returns a deduplication key for a VehicleRaw.
func vehicleKey(v *pipeline.VehicleRaw) string {
	if v.SourceURL != "" {
		return v.SourceURL
	}
	if v.VIN != nil && *v.VIN != "" {
		return "vin:" + *v.VIN
	}
	make_ := ""
	if v.Make != nil {
		make_ = *v.Make
	}
	model := ""
	if v.Model != nil {
		model = *v.Model
	}
	return fmt.Sprintf("%s|%s", make_, model)
}
