// Package e06_microdata implements extraction strategy E06 — Microdata & RDFa.
//
// # Strategy
//
// Before JSON-LD became dominant, many websites used HTML5 Microdata
// (itemscope/itemprop/itemtype) or RDFa (vocab/typeof/property) to embed
// structured data directly in HTML elements. E06 handles both formats.
//
// # Microdata
//
// Targets elements with itemtype containing a Schema.org Vehicle type:
//
//	<div itemscope itemtype="https://schema.org/Car">
//	  <span itemprop="brand">BMW</span>
//	  <span itemprop="model">320d</span>
//	  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
//	    <span itemprop="price">28500</span>
//	    <span itemprop="priceCurrency">EUR</span>
//	  </div>
//	</div>
//
// # RDFa
//
// Targets elements with typeof containing a Schema.org Vehicle type:
//
//	<div vocab="https://schema.org/" typeof="Car">
//	  <span property="brand">BMW</span>
//	  <span property="model">320d</span>
//	</div>
//
// # Page probing
//
// E06 fetches common vehicle listing paths (reusing the E01 inventory path set)
// and parses each page.  Within each page it looks for both Microdata and RDFa
// blocks. JSON-LD blocks on the same page are intentionally ignored — E01
// already handles those at higher priority.
//
// # Applicability
//
// Always returns true (any dealer site may use Microdata). In practice, the
// orchestrator will have already tried E01 (JSON-LD) at higher priority, so
// E06 only runs when JSON-LD is absent.
//
// Priority: 800 (after E04 RSS/Atom, before E07 Playwright).
package e06_microdata

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E06"
	strategyName = "Microdata / RDFa"
	maxBodyBytes = 4 << 20
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// vehicleTypeFragments matches known Schema.org vehicle type URLs.
var vehicleTypeFragments = []string{
	"schema.org/Vehicle",
	"schema.org/Car",
	"schema.org/MotorVehicle",
	"schema.org/BusOrCoach",
	"schema.org/Motorcycle",
}

// inventoryPaths are the common paths probed for vehicle listings.
var inventoryPaths = []string{
	"/",
	"/inventory",
	"/vehicles",
	"/cars",
	"/used-cars",
	"/stock",
	"/our-cars",
	"/voitures",
	"/occasion",
	"/gebrauchtwagen",
	"/gebrauchtwagen.html",
}

// Microdata is the E06 extraction strategy.
type Microdata struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a Microdata strategy with default HTTP client.
func New() *Microdata {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 1000)
}

// NewWithClient constructs a Microdata strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *Microdata {
	return &Microdata{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

func (e *Microdata) ID() string    { return strategyID }
func (e *Microdata) Name() string  { return strategyName }
func (e *Microdata) Priority() int { return pipeline.PriorityE06 }

// Applicable returns true for all dealers — any site may use Microdata/RDFa.
func (e *Microdata) Applicable(_ pipeline.Dealer) bool { return true }

// Extract fetches inventory pages and extracts Microdata + RDFa vehicle records.
func (e *Microdata) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
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
		vehicles, err := e.fetchAndParse(ctx, pageURL, baseURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "PAGE_ERROR",
				Message: err.Error(),
				URL:     pageURL,
			})
			continue
		}
		if len(vehicles) == 0 {
			continue
		}

		result.SourceURL = pageURL
		result.SourceCount++

		for _, v := range vehicles {
			key := vehicleKey(v)
			if !seenVehicles[key] {
				seenVehicles[key] = true
				result.Vehicles = append(result.Vehicles, v)
			}
		}

		if len(result.Vehicles) > 0 {
			break // stop after first page with results
		}
	}

	return result, nil
}

// fetchAndParse fetches a page and extracts Microdata + RDFa vehicle blocks.
func (e *Microdata) fetchAndParse(ctx context.Context, pageURL, baseURL string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,*/*")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", pageURL)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, pageURL)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	return parseHTML(body, pageURL, baseURL), nil
}

// parseHTML extracts all Microdata and RDFa vehicle items from an HTML page.
func parseHTML(html []byte, pageURL, baseURL string) []*pipeline.VehicleRaw {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(html)))
	if err != nil {
		return nil
	}

	var vehicles []*pipeline.VehicleRaw

	// 1. Microdata: [itemscope][itemtype*="schema.org/Car"] etc.
	doc.Find("[itemscope][itemtype]").Each(func(_ int, s *goquery.Selection) {
		itemtype, _ := s.Attr("itemtype")
		if !isVehicleType(itemtype) {
			return
		}
		if v := extractMicrodata(s, pageURL, baseURL); v != nil {
			vehicles = append(vehicles, v)
		}
	})

	// 2. RDFa: [typeof*="schema:Car"] or [typeof*="schema.org/Car"]
	doc.Find("[typeof]").Each(func(_ int, s *goquery.Selection) {
		typeof, _ := s.Attr("typeof")
		if !isVehicleTypeRDFa(typeof) {
			return
		}
		if v := extractRDFa(s, pageURL, baseURL); v != nil {
			vehicles = append(vehicles, v)
		}
	})

	return vehicles
}

// isVehicleType returns true if an itemtype URL refers to a Schema.org vehicle.
func isVehicleType(itemtype string) bool {
	for _, frag := range vehicleTypeFragments {
		if strings.Contains(itemtype, frag) {
			return true
		}
	}
	return false
}

// isVehicleTypeRDFa returns true if a typeof value refers to a vehicle type.
// Handles both "Car", "schema:Car", and full URL forms.
func isVehicleTypeRDFa(typeof string) bool {
	lower := strings.ToLower(typeof)
	for _, kw := range []string{"vehicle", "car", "motorvehicle", "motorcycle"} {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// extractMicrodata extracts a VehicleRaw from a Microdata itemscope block.
func extractMicrodata(s *goquery.Selection, pageURL, baseURL string) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{SourceURL: pageURL}

	// Collect all itemprop children (non-nested offer items handled separately).
	s.Find("[itemprop]").Each(func(_ int, prop *goquery.Selection) {
		name, _ := prop.Attr("itemprop")
		name = strings.ToLower(strings.TrimSpace(name))

		// For nested offer block, recurse.
		if name == "offers" {
			extractOfferMicrodata(prop, v)
			return
		}

		val := microdataValue(prop, baseURL)
		if val == "" {
			return
		}
		mapMicrodataProp(name, val, v)
	})

	if v.Make == nil && v.VIN == nil {
		return nil
	}
	return v
}

// extractOfferMicrodata extracts price/currency from a nested Offer scope.
func extractOfferMicrodata(offerSel *goquery.Selection, v *pipeline.VehicleRaw) {
	offerSel.Find("[itemprop]").Each(func(_ int, prop *goquery.Selection) {
		name, _ := prop.Attr("itemprop")
		name = strings.ToLower(strings.TrimSpace(name))
		val := microdataValue(prop, "")
		if val == "" {
			return
		}
		switch name {
		case "price":
			if p, err := strconv.ParseFloat(strings.ReplaceAll(val, ",", ""), 64); err == nil && p > 0 {
				v.PriceGross = &p
			}
		case "pricecurrency":
			cur := normalize.NormalizeCurrency(val)
			v.Currency = &cur
		}
	})
}

// microdataValue extracts the text value from a Microdata itemprop element.
// Handles <meta content="...">, <link href="...">, and text content.
func microdataValue(s *goquery.Selection, baseURL string) string {
	// <meta itemprop="..." content="...">
	if content, exists := s.Attr("content"); exists {
		return strings.TrimSpace(content)
	}
	// <link itemprop="..." href="...">
	if href, exists := s.Attr("href"); exists && s.Is("link") {
		if baseURL != "" {
			return normalize.CanonicalizePhotoURL(href, baseURL)
		}
		return href
	}
	// <img itemprop="image" src="...">
	if src, exists := s.Attr("src"); exists && s.Is("img") {
		if baseURL != "" {
			return normalize.CanonicalizePhotoURL(src, baseURL)
		}
		return src
	}
	return strings.TrimSpace(s.Text())
}

// mapMicrodataProp maps a Schema.org itemprop name to a VehicleRaw field.
func mapMicrodataProp(name, val string, v *pipeline.VehicleRaw) {
	switch name {
	case "vehicleidentificationnumber", "vin":
		if vin := normalize.NormalizeVIN(val); vin != "" {
			v.VIN = &vin
		}
	case "brand", "manufacturer":
		mk := normalize.NormalizeMake(val)
		v.Make = &mk
	case "model":
		v.Model = &val
	case "vehiclemodelyear", "yearmade", "year":
		if yr, err := strconv.Atoi(val); err == nil && yr > 1900 && yr < 2100 {
			v.Year = &yr
		}
	case "mileagefromodometer", "mileage", "odometer":
		// Value may be "45000 km" or just "45000"
		raw := strings.Fields(val)
		if len(raw) > 0 {
			if km, err := strconv.Atoi(strings.ReplaceAll(raw[0], ",", "")); err == nil && km > 0 {
				v.Mileage = &km
			}
		}
	case "color", "vehiclecolor", "colour":
		v.Color = &val
	case "fueltype", "fuel":
		fuel := normalize.NormalizeFuelType(val)
		v.FuelType = &fuel
	case "vehicletransmission", "transmission":
		tx := normalize.NormalizeTransmission(val)
		v.Transmission = &tx
	case "bodytype":
		bt := normalize.NormalizeBodyType(val)
		v.BodyType = &bt
	case "name":
		// "name" at Vehicle level often contains "Make Model Year"
		// Only use it if no explicit make/model yet.
		if v.Make == nil {
			parseTitleHeuristic(val, v)
		}
	case "url", "link":
		if v.SourceURL == "" {
			v.SourceURL = val
		}
	case "image":
		v.ImageURLs = append(v.ImageURLs, val)
	}
}

// extractRDFa extracts a VehicleRaw from an RDFa typeof block.
func extractRDFa(s *goquery.Selection, pageURL, baseURL string) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{SourceURL: pageURL}

	s.Find("[property]").Each(func(_ int, prop *goquery.Selection) {
		propAttr, _ := prop.Attr("property")
		// RDFa property may be "schema:brand", "og:title", "vehicle:make", or bare "brand"
		// Normalise by stripping any namespace prefix.
		parts := strings.SplitN(propAttr, ":", 2)
		name := strings.ToLower(strings.TrimSpace(parts[len(parts)-1]))

		val := rdFaValue(prop, baseURL)
		if val == "" {
			return
		}
		// RDFa uses the same Schema.org property names as Microdata.
		mapMicrodataProp(name, val, v)
	})

	if v.Make == nil && v.VIN == nil {
		return nil
	}
	return v
}

// rdFaValue extracts the text/content/resource value of an RDFa property element.
func rdFaValue(s *goquery.Selection, baseURL string) string {
	if content, exists := s.Attr("content"); exists {
		return strings.TrimSpace(content)
	}
	if resource, exists := s.Attr("resource"); exists {
		return strings.TrimSpace(resource)
	}
	return strings.TrimSpace(s.Text())
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
	return make_ + "|" + model
}

// parseTitleHeuristic tries to extract make/model/year from a free-text title.
func parseTitleHeuristic(title string, v *pipeline.VehicleRaw) {
	knownMakes := []string{
		"Abarth", "Alfa Romeo", "Audi", "BMW", "Citroen", "Citroën", "Cupra",
		"Dacia", "DS", "Ferrari", "Fiat", "Ford", "Honda", "Hyundai",
		"Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Mazda",
		"Mercedes", "Mercedes-Benz", "MINI", "Mini", "Mitsubishi",
		"Nissan", "Opel", "Peugeot", "Porsche", "Renault", "SEAT", "Seat",
		"Škoda", "Skoda", "Smart", "Subaru", "Suzuki", "Tesla", "Toyota",
		"Volkswagen", "Volvo", "VW",
	}
	upper := strings.ToUpper(title)
	for _, mk := range knownMakes {
		if strings.Contains(upper, strings.ToUpper(mk)) {
			m := mk
			v.Make = &m
			idx := strings.Index(upper, strings.ToUpper(mk))
			rest := strings.TrimSpace(title[idx+len(mk):])
			if rest != "" {
				words := strings.Fields(rest)
				if len(words) > 0 {
					model := words[0]
					v.Model = &model
				}
			}
			break
		}
	}
}
