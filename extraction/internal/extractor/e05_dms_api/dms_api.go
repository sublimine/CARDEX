// Package e05_dms_api implements extraction strategy E05 — DMS Hosted API.
//
// # Strategy
//
// Dealers hosted on a known DMS (Dealer Management System) provider expose a
// vendor-specific JSON or XML inventory endpoint. Familia E (from the discovery
// phase) records the DMSProvider in the dealer record. E05 looks up a matching
// adapter for that provider and calls the known endpoint directly, bypassing
// the need for any HTML crawling.
//
// # Adapters (Sprint 17)
//
//   - CDK Global:        /cdk-portal/api/inventory
//   - Reynolds & Reynolds: /api/vehicles?format=json
//   - incadea:           /incadea-cms/inventory
//   - DealerSocket:      /dealersocket/api/listings
//   - Cox Automotive:    /coxauto/api/inventory
//   - Modix:             /modix-platform/inventory
//   - Carmen:            /carmen-export.json  (root array, FR fields)
//   - AutoLine:          /autoline-feed.xml   (XML)
//
// # JSON field mapping
//
// Most adapters use a shared flexible mapper that understands common field name
// variants across DMS platforms (make/Make/marque/Marke, etc.). Only AutoLine
// requires a separate XML decoder.
//
// # Applicability
//
//   - dealer.DMSProvider must be non-empty.
//   - At least one registered adapter must match dealer.DMSProvider.
//
// Priority: 1050 (between E02 CMS REST and E03 Sitemap XML).
package e05_dms_api

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E05"
	strategyName = "DMS Hosted API"
	maxBodyBytes = 8 << 20 // 8 MiB
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// dmsAdapter describes a single DMS provider with its endpoint patterns.
type dmsAdapter struct {
	// providerKeywords are lowercased substrings matched against dealer.DMSProvider.
	providerKeywords []string
	providerName     string
	// paths are the endpoint URL paths tried in order until one returns 200.
	paths []string
	// format is "json" or "xml".
	format string
}

// registeredAdapters holds all known DMS adapters.
var registeredAdapters = []*dmsAdapter{
	{
		providerKeywords: []string{"cdk"},
		providerName:     "CDK Global",
		paths:            []string{"/cdk-portal/api/inventory", "/cdk/api/inventory"},
		format:           "json",
	},
	{
		providerKeywords: []string{"reynolds", "r&r", "reyrey"},
		providerName:     "Reynolds & Reynolds",
		paths:            []string{"/api/vehicles?format=json", "/rr/api/vehicles"},
		format:           "json",
	},
	{
		providerKeywords: []string{"incadea"},
		providerName:     "incadea",
		paths:            []string{"/incadea-cms/inventory", "/incadea/inventory"},
		format:           "json",
	},
	{
		providerKeywords: []string{"dealersocket", "dealer_socket"},
		providerName:     "DealerSocket",
		paths:            []string{"/dealersocket/api/listings", "/ds/api/listings"},
		format:           "json",
	},
	{
		providerKeywords: []string{"cox", "vinsolutions", "autotrader"},
		providerName:     "Cox Automotive",
		paths:            []string{"/coxauto/api/inventory", "/cox/api/inventory"},
		format:           "json",
	},
	{
		providerKeywords: []string{"modix"},
		providerName:     "Modix",
		paths:            []string{"/modix-platform/inventory", "/modix/inventory"},
		format:           "json",
	},
	{
		providerKeywords: []string{"carmen"},
		providerName:     "Carmen",
		paths:            []string{"/carmen-export.json", "/export/carmen.json"},
		format:           "json",
	},
	{
		providerKeywords: []string{"autoline"},
		providerName:     "AutoLine",
		paths:            []string{"/autoline-feed.xml", "/autoline/feed.xml"},
		format:           "xml",
	},
}

// findAdapter returns the first adapter whose providerKeywords match the dealer's
// DMSProvider field (case-insensitive substring match).
func findAdapter(dmsProvider string) *dmsAdapter {
	lower := strings.ToLower(strings.TrimSpace(dmsProvider))
	for _, a := range registeredAdapters {
		for _, kw := range a.providerKeywords {
			if strings.Contains(lower, kw) {
				return a
			}
		}
	}
	return nil
}

// -- Strategy -----------------------------------------------------------------

// DMSAPI is the E05 extraction strategy.
type DMSAPI struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a DMSAPI strategy with default HTTP client.
func New() *DMSAPI {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 1000)
}

// NewWithClient constructs a DMSAPI strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *DMSAPI {
	return &DMSAPI{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

func (e *DMSAPI) ID() string       { return strategyID }
func (e *DMSAPI) Name() string     { return strategyName }
func (e *DMSAPI) Priority() int    { return pipeline.PriorityE05 }

// Applicable returns true if the dealer has a known DMSProvider.
func (e *DMSAPI) Applicable(dealer pipeline.Dealer) bool {
	if dealer.DMSProvider == "" {
		return false
	}
	return findAdapter(dealer.DMSProvider) != nil
}

// Extract calls the DMS provider's inventory endpoint and maps the response.
func (e *DMSAPI) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	adapter := findAdapter(dealer.DMSProvider)
	if adapter == nil {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_ADAPTER",
			Message: fmt.Sprintf("no DMS adapter for provider %q", dealer.DMSProvider),
		})
		return result, nil
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// Try each path until one returns data.
	for _, path := range adapter.paths {
		if ctx.Err() != nil {
			break
		}
		u := baseURL + path
		vehicles, err := e.fetchEndpoint(ctx, u, adapter.format)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "FETCH_ERROR",
				Message: err.Error(),
				URL:     u,
			})
			continue
		}
		if len(vehicles) > 0 {
			result.Vehicles = vehicles
			result.SourceURL = u
			result.SourceCount = 1
			return result, nil
		}
	}

	return result, nil
}

// fetchEndpoint fetches a DMS endpoint and parses the response.
func (e *DMSAPI) fetchEndpoint(ctx context.Context, u, format string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	if format == "xml" {
		req.Header.Set("Accept", "application/xml,text/xml,*/*")
	} else {
		req.Header.Set("Accept", "application/json,*/*")
	}

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", u)
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // path not found — try next
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, u)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	if format == "xml" {
		return parseAutoLineXML(body)
	}
	return parseFlexibleJSON(body)
}

// -- JSON parsing -------------------------------------------------------------

// parseFlexibleJSON extracts vehicles from a DMS JSON response.
// It handles both root-array responses (Carmen) and root-object responses
// with common inventory array keys (inventory, vehicles, items, listings, results, data).
func parseFlexibleJSON(body []byte) ([]*pipeline.VehicleRaw, error) {
	// Try root array first.
	var arr []json.RawMessage
	if err := json.Unmarshal(body, &arr); err == nil {
		return mapVehicleArray(arr), nil
	}

	// Try root object with known array keys.
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(body, &obj); err != nil {
		return nil, fmt.Errorf("parse JSON: %w", err)
	}

	for _, key := range []string{"inventory", "vehicles", "items", "listings", "results", "data", "records"} {
		if raw, ok := obj[key]; ok {
			var arr []json.RawMessage
			if err := json.Unmarshal(raw, &arr); err == nil {
				return mapVehicleArray(arr), nil
			}
		}
	}
	return nil, nil
}

// mapVehicleArray maps a slice of raw JSON objects to VehicleRaw records.
func mapVehicleArray(items []json.RawMessage) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw
	for _, raw := range items {
		var m map[string]json.RawMessage
		if err := json.Unmarshal(raw, &m); err != nil {
			continue
		}
		if v := extractVehicleFromMap(m); v != nil {
			vehicles = append(vehicles, v)
		}
	}
	return vehicles
}

// extractVehicleFromMap maps a flat/nested JSON object to a VehicleRaw.
// Field aliases cover CDK, Reynolds, incadea, DealerSocket, Cox, Modix, Carmen.
func extractVehicleFromMap(m map[string]json.RawMessage) *pipeline.VehicleRaw {
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
					f, _ = strconv.ParseFloat(strings.TrimSpace(s), 64)
					if f > 0 {
						return f
					}
				}
			}
		}
		return 0
	}

	getInt := func(keys ...string) int {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var i int
				if json.Unmarshal(raw, &i) == nil && i > 0 {
					return i
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
	if vin := normalize.NormalizeVIN(getString("vin", "VIN", "vehicleVin", "vehicle_vin")); vin != "" {
		v.VIN = &vin
	}

	// Make.
	if mk := getString("make", "Make", "manufacturer", "marque", "Marke", "vehicleMake", "brand", "Brand"); mk != "" {
		mk = normalize.NormalizeMake(mk)
		v.Make = &mk
	}

	// Model.
	if model := getString("model", "Model", "modelName", "modele", "Modell", "vehicleModel", "model_name"); model != "" {
		v.Model = &model
	}

	// Year.
	if yr := getInt("year", "Year", "ModelYear", "modelYear", "annee", "Baujahr", "vehicleYear", "manufacture_year"); yr > 1900 && yr < 2100 {
		v.Year = &yr
	}

	// Mileage — try direct field, then nested odometer.
	if km := getInt("mileage", "Mileage", "OdometerReading", "vehicleMileage", "kilometrage", "km", "odometer_value", "kilometers"); km > 0 {
		v.Mileage = &km
	} else if raw, ok := m["odometer"]; ok {
		// Cox: {"odometer": {"value": 30000, "units": "mi"}}
		var nested map[string]json.RawMessage
		if json.Unmarshal(raw, &nested) == nil {
			if km2 := getIntFromMap(nested, "value", "kilometers", "km"); km2 > 0 {
				v.Mileage = &km2
			}
		}
	}

	// Price — try direct, then nested.
	if p := getFloat("price", "Price", "ListPrice", "askingPrice", "prix", "Preis", "list_price", "retail_price"); p > 0 {
		v.PriceGross = &p
	} else if raw, ok := m["price"]; ok {
		var nested map[string]json.RawMessage
		if json.Unmarshal(raw, &nested) == nil {
			// incadea: {"price": {"value": 18500, "currency": "EUR"}}
			if p2 := getFloatFromMap(nested, "value", "amount", "net"); p2 > 0 {
				v.PriceGross = &p2
			}
		}
	}

	// Currency.
	if cur := getString("currency", "Currency", "priceCurrency", "devise"); cur != "" {
		cur = normalize.NormalizeCurrency(cur)
		v.Currency = &cur
	}

	// Color.
	if col := getString("color", "Color", "colour", "couleur", "Farbe"); col != "" {
		v.Color = &col
	}

	// Fuel.
	if fuel := normalize.NormalizeFuelType(getString("fuel", "fuelType", "FuelType", "carburant", "Kraftstoff")); fuel != "" {
		v.FuelType = &fuel
	}

	// Transmission.
	if tx := normalize.NormalizeTransmission(getString("transmission", "Transmission", "boite", "Getriebe")); tx != "" {
		v.Transmission = &tx
	}

	// SourceURL.
	if url := getString("url", "URL", "link", "listingUrl", "vehicleUrl", "lien"); url != "" {
		v.SourceURL = url
	}

	// SourceListingID.
	if id := getString("id", "Id", "listingId", "vehicleId", "stock_number", "stockNumber"); id != "" {
		v.SourceListingID = id
	}

	if v.Make == nil && v.VIN == nil {
		return nil // not a vehicle record
	}
	return v
}

// getIntFromMap is a helper for extracting int from a nested map.
func getIntFromMap(m map[string]json.RawMessage, keys ...string) int {
	for _, k := range keys {
		if raw, ok := m[k]; ok {
			var i int
			if json.Unmarshal(raw, &i) == nil && i > 0 {
				return i
			}
			var f float64
			if json.Unmarshal(raw, &f) == nil && f > 0 {
				return int(f)
			}
		}
	}
	return 0
}

// getFloatFromMap is a helper for extracting float from a nested map.
func getFloatFromMap(m map[string]json.RawMessage, keys ...string) float64 {
	for _, k := range keys {
		if raw, ok := m[k]; ok {
			var f float64
			if json.Unmarshal(raw, &f) == nil && f > 0 {
				return f
			}
		}
	}
	return 0
}

// -- AutoLine XML parsing -----------------------------------------------------

type autoLineDoc struct {
	XMLName  xml.Name          `xml:"vehicles"`
	Vehicles []autoLineVehicle `xml:"vehicle"`
}

type autoLineVehicle struct {
	VIN      string  `xml:"vin"`
	Make     string  `xml:"make"`
	Model    string  `xml:"model"`
	Year     int     `xml:"year"`
	Mileage  int     `xml:"mileage"`
	Price    float64 `xml:"price"`
	Color    string  `xml:"color"`
	Fuel     string  `xml:"fuel"`
	Currency string  `xml:"currency"`
}

func parseAutoLineXML(body []byte) ([]*pipeline.VehicleRaw, error) {
	var doc autoLineDoc
	if err := xml.Unmarshal(body, &doc); err != nil {
		return nil, fmt.Errorf("autoline XML: %w", err)
	}
	var vehicles []*pipeline.VehicleRaw
	for _, av := range doc.Vehicles {
		v := &pipeline.VehicleRaw{}
		if vin := normalize.NormalizeVIN(av.VIN); vin != "" {
			v.VIN = &vin
		}
		if av.Make != "" {
			mk := normalize.NormalizeMake(av.Make)
			v.Make = &mk
		}
		if av.Model != "" {
			v.Model = &av.Model
		}
		if av.Year > 1900 {
			v.Year = &av.Year
		}
		if av.Mileage > 0 {
			v.Mileage = &av.Mileage
		}
		if av.Price > 0 {
			v.PriceGross = &av.Price
		}
		if av.Color != "" {
			v.Color = &av.Color
		}
		if fuel := normalize.NormalizeFuelType(av.Fuel); fuel != "" {
			v.FuelType = &fuel
		}
		if av.Currency != "" {
			cur := normalize.NormalizeCurrency(av.Currency)
			v.Currency = &cur
		}
		if v.Make == nil && v.VIN == nil {
			continue
		}
		vehicles = append(vehicles, v)
	}
	return vehicles, nil
}
