// Package e09_excel implements extraction strategy E09 — Excel/CSV Feeds.
//
// # Strategy
//
// Dealers with simple DMS integrations often export their inventory as a
// spreadsheet or CSV file. E09 discovers such files from homepage links and
// common probe paths, then parses them into vehicle records.
//
// # Supported formats
//
//   - XLSX (Excel 2007+): parsed via github.com/xuri/excelize/v2
//   - CSV (comma-separated values): parsed via stdlib encoding/csv
//
// # Header detection
//
// Row 0 is inspected for vehicle field keywords (VIN, Make, Model, Year, Price,
// Mileage and multi-language variants). Matching is fuzzy: partial substring
// matches are accepted to handle local-language headers (e.g. "Marque" → Make).
//
// Priority: 700 (same tier as E08 PDF).
package e09_excel

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	excelize "github.com/xuri/excelize/v2"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E09"
	strategyName = "Excel/CSV Feed"
	maxFileBytes = 16 << 20 // 16 MiB
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// probePaths are the candidate paths probed for Excel/CSV inventory exports.
var probePaths = []string{
	"/inventory.xlsx", "/inventory.csv",
	"/export.xlsx", "/export.csv",
	"/cars.xlsx", "/cars.csv",
	"/voitures.xlsx", "/voitures.csv",
	"/coches.xlsx", "/coches.csv",
	"/fahrzeuge.xlsx", "/fahrzeuge.csv",
	"/vehicle-list.xlsx", "/vehicle-list.csv",
	"/feeds/inventory.csv", "/feeds/cars.xlsx",
}

// fileKeywords are used when scanning homepage links for spreadsheet files.
var fileKeywords = []string{
	"inventory", "inventaire", "catalog", "catalogue", "fahrzeug",
	"voiture", "coche", "vehicle", "cars", "export", "listing", "stock",
}

// Column header aliases for fuzzy matching (value: canonical field name).
var colAliases = map[string]string{
	// VIN
	"vin": "vin", "chassis": "vin", "serial": "vin",
	// Make
	"make": "make", "brand": "make", "marque": "make", "marke": "make", "marca": "make",
	// Model
	"model": "model", "modele": "model", "modell": "model", "modelo": "model",
	// Year
	"year": "year", "annee": "year", "baujahr": "year", "ano": "year",
	"year of": "year", "model year": "year",
	// Mileage
	"mileage": "mileage", "odometer": "mileage", "km": "mileage",
	"kilometrage": "mileage", "kilometre": "mileage",
	// Price
	"price": "price", "prix": "price", "preis": "price", "precio": "price",
	"list price": "price", "asking": "price",
	// Color
	"color": "color", "colour": "color", "couleur": "color", "farbe": "color",
	// Fuel
	"fuel": "fuel", "carburant": "fuel", "kraftstoff": "fuel",
}

// ExcelCSV is the E09 extraction strategy.
type ExcelCSV struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs an ExcelCSV strategy with default HTTP client.
func New() *ExcelCSV {
	return NewWithClient(&http.Client{Timeout: 30 * time.Second}, 1000)
}

// NewWithClient constructs an ExcelCSV strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *ExcelCSV {
	return &ExcelCSV{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

func (e *ExcelCSV) ID() string    { return strategyID }
func (e *ExcelCSV) Name() string  { return strategyName }
func (e *ExcelCSV) Priority() int { return pipeline.PriorityE09 }

// Applicable returns true for all dealers.
func (e *ExcelCSV) Applicable(_ pipeline.Dealer) bool { return true }

// Extract discovers Excel/CSV files and extracts vehicle records.
func (e *ExcelCSV) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// 1. Discover feed URLs.
	feedURLs := e.discoverFeeds(ctx, baseURL)
	if len(feedURLs) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_FEED",
			Message: "no Excel/CSV feed found via homepage links or probe paths",
			URL:     baseURL,
		})
		return result, nil
	}

	seenVehicles := map[string]bool{}

	for i, feedURL := range feedURLs {
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

		vehicles, err := e.fetchAndParse(ctx, feedURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "FEED_ERROR",
				Message: err.Error(),
				URL:     feedURL,
			})
			continue
		}
		if len(vehicles) == 0 {
			continue
		}

		result.SourceURL = feedURL
		result.SourceCount++

		for _, v := range vehicles {
			key := vehicleKey(v)
			if !seenVehicles[key] {
				seenVehicles[key] = true
				result.Vehicles = append(result.Vehicles, v)
			}
		}
		break
	}

	return result, nil
}

// discoverFeeds finds spreadsheet URLs from the homepage and probe paths.
func (e *ExcelCSV) discoverFeeds(ctx context.Context, baseURL string) []string {
	// 1. Homepage link scan.
	links := e.scanHomepageLinks(ctx, baseURL)
	if len(links) > 0 {
		return links
	}

	// 2. Probe common paths.
	for _, path := range probePaths {
		if ctx.Err() != nil {
			break
		}
		u := baseURL + path
		if e.probeURL(ctx, u) {
			return []string{u}
		}
	}
	return nil
}

// scanHomepageLinks finds spreadsheet links with vehicle keywords in homepage HTML.
func (e *ExcelCSV) scanHomepageLinks(ctx context.Context, baseURL string) []string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := e.client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return nil
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(body)))
	if err != nil {
		return nil
	}

	var found []string
	doc.Find("a[href]").Each(func(_ int, s *goquery.Selection) {
		href, _ := s.Attr("href")
		lower := strings.ToLower(href)
		if !strings.HasSuffix(lower, ".xlsx") && !strings.HasSuffix(lower, ".csv") {
			return
		}
		linkText := strings.ToLower(s.Text() + " " + href)
		for _, kw := range fileKeywords {
			if strings.Contains(linkText, kw) {
				abs := normalize.CanonicalizePhotoURL(href, baseURL)
				found = append(found, abs)
				return
			}
		}
	})
	return found
}

// probeURL returns true if a HEAD request returns HTTP 200.
func (e *ExcelCSV) probeURL(ctx context.Context, u string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, u, nil)
	if err != nil {
		return false
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := e.client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// fetchAndParse downloads a spreadsheet and parses vehicle records.
func (e *ExcelCSV) fetchAndParse(ctx context.Context, u string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", u)
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, u)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxFileBytes))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	lower := strings.ToLower(u)
	if strings.HasSuffix(lower, ".xlsx") || strings.Contains(resp.Header.Get("Content-Type"), "spreadsheet") {
		return parseXLSX(body)
	}
	return parseCSV(body)
}

// -- CSV parsing --------------------------------------------------------------

// parseCSV parses a CSV file into vehicle records.
func parseCSV(data []byte) ([]*pipeline.VehicleRaw, error) {
	r := csv.NewReader(bytes.NewReader(data))
	r.LazyQuotes = true
	r.TrimLeadingSpace = true

	rows, err := r.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("csv.ReadAll: %w", err)
	}
	if len(rows) < 2 {
		return nil, nil // header + no data
	}
	colMap := detectHeaderRow(rows[0])
	return mapSpreadsheetRows(rows[1:], colMap), nil
}

// -- XLSX parsing -------------------------------------------------------------

// parseXLSX parses an XLSX file's first sheet into vehicle records.
func parseXLSX(data []byte) ([]*pipeline.VehicleRaw, error) {
	f, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("excelize.OpenReader: %w", err)
	}
	defer f.Close()

	sheetName := f.GetSheetName(0)
	rows, err := f.GetRows(sheetName)
	if err != nil {
		return nil, fmt.Errorf("xlsx GetRows: %w", err)
	}
	if len(rows) < 2 {
		return nil, nil
	}
	colMap := detectHeaderRow(rows[0])
	return mapSpreadsheetRows(rows[1:], colMap), nil
}

// -- Shared header/row mapping ------------------------------------------------

// detectHeaderRow builds a canonical-field-name → column-index map from a header row.
func detectHeaderRow(headers []string) map[string]int {
	colMap := map[string]int{}
	for i, h := range headers {
		lower := strings.ToLower(strings.TrimSpace(h))
		for alias, canonical := range colAliases {
			if strings.Contains(lower, alias) {
				if _, exists := colMap[canonical]; !exists {
					colMap[canonical] = i
				}
			}
		}
	}
	return colMap
}

// mapSpreadsheetRows maps data rows to VehicleRaw records using the column map.
func mapSpreadsheetRows(rows [][]string, colMap map[string]int) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw
	for _, row := range rows {
		if len(row) == 0 {
			continue
		}
		v := &pipeline.VehicleRaw{}

		get := func(field string) string {
			if idx, ok := colMap[field]; ok && idx < len(row) {
				return strings.TrimSpace(row[idx])
			}
			return ""
		}

		if raw := get("vin"); raw != "" {
			if vin := normalize.NormalizeVIN(raw); vin != "" {
				v.VIN = &vin
			}
		}
		if raw := get("make"); raw != "" {
			mk := normalize.NormalizeMake(raw)
			v.Make = &mk
		}
		if raw := get("model"); raw != "" {
			v.Model = &raw
		}
		if raw := get("year"); raw != "" {
			if yr, err := strconv.Atoi(raw); err == nil && yr > 1900 && yr < 2100 {
				v.Year = &yr
			}
		}
		if raw := get("mileage"); raw != "" {
			digits := strings.Map(func(r rune) rune {
				if r >= '0' && r <= '9' {
					return r
				}
				return -1
			}, raw)
			if km, err := strconv.Atoi(digits); err == nil && km > 0 {
				v.Mileage = &km
			}
		}
		if raw := get("price"); raw != "" {
			clean := strings.Map(func(r rune) rune {
				if (r >= '0' && r <= '9') || r == '.' || r == ',' {
					return r
				}
				return -1
			}, raw)
			if i := strings.LastIndex(clean, ","); i >= 0 {
				clean = strings.ReplaceAll(clean[:i], ".", "") + "." + clean[i+1:]
			}
			var p float64
			fmt.Sscanf(clean, "%f", &p)
			if p > 0 {
				v.PriceGross = &p
			}
		}
		if raw := get("color"); raw != "" {
			v.Color = &raw
		}
		if raw := get("fuel"); raw != "" {
			fuel := normalize.NormalizeFuelType(raw)
			v.FuelType = &fuel
		}

		if v.Make == nil && v.VIN == nil {
			continue
		}
		vehicles = append(vehicles, v)
	}
	return vehicles
}

// vehicleKey returns a deduplication key for a VehicleRaw.
func vehicleKey(v *pipeline.VehicleRaw) string {
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
	return make_ + "|" + model
}
