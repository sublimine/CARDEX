// Package e01_jsonld implements extraction strategy E01 — JSON-LD Schema.org
// Vehicle inline.
//
// # Strategy
//
// Schema.org defines Vehicle/Car/MotorVehicle types that webmasters embed as
// JSON-LD blocks in HTML pages. This markup is designed for search engines to
// consume, making it the highest-quality extraction source: no HTML parsing
// fragility, no rendering required, and the data is intentionally published for
// automated consumption.
//
// # Algorithm
//
//  1. Fetch the dealer's base URL and common inventory page paths.
//  2. Extract all <script type="application/ld+json"> blocks from each page.
//  3. Walk each block looking for @type == Vehicle|Car|MotorVehicle|BusOrCoach.
//     Also handles ItemList and OfferCatalog wrapper types.
//  4. Map Schema.org properties to VehicleRaw fields.
//  5. Resolve relative photo URLs to absolute.
//
// # Applicable
//
// E01 is attempted for any dealer where:
//   - ExtractionHints contains "schema_org_detected" (Familia D D.1), OR
//   - PlatformType is "CMS_WORDPRESS" (WP + Yoast/RankMath often outputs schema), OR
//   - PlatformType is "UNKNOWN" or "" (try as cheap fallback — no extra cost if empty)
//
// # Rate limits
//
// 2 s between pages of the same dealer (configurable via RateLimitMs).
package e01_jsonld

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E01"
	strategyName = "JSON-LD Schema.org Vehicle inline"
	maxBodyBytes = 2 << 20  // 2 MiB per page
	maxPages     = 10       // maximum inventory pages to fetch per dealer
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// inventoryPaths is the list of URL paths to probe for inventory pages,
// ordered by estimated frequency across DE/FR/ES/NL/BE/CH markets.
var inventoryPaths = []string{
	"",             // homepage itself (some dealers list cars here)
	"/inventory",
	"/stock",
	"/occasions",
	"/voitures-occasion",
	"/vehicules-occasion",
	"/gebrauchtwagen",
	"/occasion",
	"/used-cars",
	"/used",
	"/pre-owned",
	"/vehiculos-usados",
	"/coches-de-ocasion",
	"/occasions.html",
	"/inventory.html",
	"/auto-usate",
}

// vehicleTypes is the set of Schema.org @type values that indicate a vehicle.
var vehicleTypes = map[string]bool{
	"Vehicle": true, "Car": true, "MotorVehicle": true,
	"BusOrCoach": true, "Motorcycle": true,
}

// containerTypes wraps one or more vehicles.
var containerTypes = map[string]bool{
	"ItemList": true, "OfferCatalog": true, "AutoDealer": true,
}

// JSONLD is the E01 extraction strategy.
type JSONLD struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a JSONLD strategy with default HTTP client.
func New() *JSONLD {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 2000)
}

// NewWithClient constructs a JSONLD strategy with a custom HTTP client and
// rate limit. Used in tests.
func NewWithClient(c *http.Client, rateLimitMs int) *JSONLD {
	return &JSONLD{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

// ID returns "E01".
func (e *JSONLD) ID() string { return strategyID }

// Name returns the human-readable strategy name.
func (e *JSONLD) Name() string { return strategyName }

// Priority returns 1200 (highest in cascade).
func (e *JSONLD) Priority() int { return pipeline.PriorityE01 }

// Applicable returns true for dealers that are likely to have Schema.org markup.
func (e *JSONLD) Applicable(dealer pipeline.Dealer) bool {
	for _, hint := range dealer.ExtractionHints {
		if hint == "schema_org_detected" {
			return true
		}
	}
	// Broad applicability: WordPress dealers frequently have schema.org from
	// SEO plugins (Yoast, RankMath). Unknown platform = try it cheap.
	pt := strings.ToUpper(dealer.PlatformType)
	return pt == "CMS_WORDPRESS" || pt == "UNKNOWN" || pt == "" ||
		strings.Contains(strings.ToLower(dealer.CMSDetected), "wordpress")
}

// Extract fetches inventory pages and extracts JSON-LD vehicle records.
// Pages are fetched in order until vehicles are found; cross-page deduplication
// prevents the same vehicle from appearing multiple times in the result.
func (e *JSONLD) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	seenPages := map[string]bool{}
	seenVehicles := map[string]bool{} // cross-page vehicle dedup

	for i, path := range inventoryPaths {
		if ctx.Err() != nil {
			break
		}
		// Once we've found vehicles AND tried at least one inventory path (i>0),
		// stop — we've got the catalog.
		if len(result.Vehicles) > 0 && i > 0 {
			break
		}
		if result.SourceCount >= maxPages {
			break
		}

		pageURL := baseURL + path
		if seenPages[pageURL] {
			continue
		}
		seenPages[pageURL] = true

		if i > 0 {
			sleep := e.rateLimitMs
			if sleep <= 0 {
				sleep = 50 // minimum 50 ms (tests use 0 which floors to 50)
			}
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(time.Duration(sleep) * time.Millisecond):
			}
		}

		vehicles, err := e.fetchAndExtract(ctx, pageURL, baseURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "FETCH_ERROR",
				Message: err.Error(),
				URL:     pageURL,
			})
			continue
		}
		result.SourceCount++

		// Deduplicate vehicles across pages.
		for _, v := range vehicles {
			key := vehicleKey(v)
			if !seenVehicles[key] {
				seenVehicles[key] = true
				result.Vehicles = append(result.Vehicles, v)
			}
		}

		if len(vehicles) > 0 && result.SourceURL == "" {
			result.SourceURL = pageURL
		}
	}

done:
	if result.SourceURL == "" && result.SourceCount > 0 {
		result.SourceURL = baseURL
	}
	return result, nil
}

// vehicleKey returns a deduplication key for a vehicle.
func vehicleKey(v *pipeline.VehicleRaw) string {
	if v.SourceURL != "" {
		return v.SourceURL
	}
	vin := derefStr(v.VIN)
	if vin != "" {
		return "vin:" + vin
	}
	return derefStr(v.Make) + "|" + derefStr(v.Model) + "|" + derefStr((*string)(nil))
}

// fetchAndExtract fetches a single page and extracts all JSON-LD vehicles.
func (e *JSONLD) fetchAndExtract(ctx context.Context, pageURL, baseURL string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // 404 = path doesn't exist, not an error
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429 rate limited: %s", pageURL)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, pageURL)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	return extractFromHTML(body, baseURL)
}

// extractFromHTML parses HTML and extracts Vehicle records from all JSON-LD blocks.
func extractFromHTML(html []byte, baseURL string) ([]*pipeline.VehicleRaw, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(html)))
	if err != nil {
		return nil, fmt.Errorf("goquery parse: %w", err)
	}

	var vehicles []*pipeline.VehicleRaw
	seen := map[string]bool{}

	doc.Find(`script[type="application/ld+json"]`).Each(func(_ int, s *goquery.Selection) {
		raw := strings.TrimSpace(s.Text())
		if raw == "" {
			return
		}
		extracted := parseJSONLD(raw, baseURL)
		for _, v := range extracted {
			key := v.SourceURL
			if key == "" {
				key = derefStr(v.VIN) + "|" + derefStr(v.Make) + "|" + derefStr(v.Model)
			}
			if !seen[key] {
				seen[key] = true
				vehicles = append(vehicles, v)
			}
		}
	})

	return vehicles, nil
}

// parseJSONLD parses a raw JSON-LD string and extracts Vehicle records.
// Gracefully handles malformed JSON and unsupported @type values.
func parseJSONLD(raw, baseURL string) []*pipeline.VehicleRaw {
	// Try to unmarshal as array first, then as single object.
	var nodes []json.RawMessage
	if err := json.Unmarshal([]byte(raw), &nodes); err != nil {
		// Not an array — wrap as single-element.
		nodes = []json.RawMessage{json.RawMessage(raw)}
	}

	var vehicles []*pipeline.VehicleRaw
	for _, node := range nodes {
		extracted := walkNode(node, baseURL)
		vehicles = append(vehicles, extracted...)
	}
	return vehicles
}

// walkNode recursively walks a JSON-LD node extracting Vehicle records.
func walkNode(node json.RawMessage, baseURL string) []*pipeline.VehicleRaw {
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(node, &obj); err != nil {
		return nil
	}

	typ := extractType(obj)

	if vehicleTypes[typ] {
		v := mapVehicleNode(obj, baseURL)
		if v != nil {
			return []*pipeline.VehicleRaw{v}
		}
		return nil
	}

	if containerTypes[typ] {
		return walkContainer(obj, baseURL)
	}

	// Unknown type — try children anyway in case the schema is nested.
	return walkContainer(obj, baseURL)
}

// walkContainer descends into container types (ItemList, OfferCatalog, AutoDealer).
func walkContainer(obj map[string]json.RawMessage, baseURL string) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw

	// ItemList / OfferCatalog: itemListElement
	if raw, ok := obj["itemListElement"]; ok {
		var items []json.RawMessage
		if err := json.Unmarshal(raw, &items); err != nil {
			// Single item.
			items = []json.RawMessage{raw}
		}
		for _, item := range items {
			vehicles = append(vehicles, walkNode(item, baseURL)...)
		}
	}

	// AutoDealer: hasOfferCatalog
	if raw, ok := obj["hasOfferCatalog"]; ok {
		vehicles = append(vehicles, walkNode(raw, baseURL)...)
	}

	// makesOffer / offers (list of vehicles)
	for _, key := range []string{"makesOffer", "offers"} {
		if raw, ok := obj[key]; ok {
			var items []json.RawMessage
			if err := json.Unmarshal(raw, &items); err != nil {
				items = []json.RawMessage{raw}
			}
			for _, item := range items {
				vehicles = append(vehicles, walkNode(item, baseURL)...)
			}
		}
	}

	// "item" field (ListItem wrapper)
	if raw, ok := obj["item"]; ok {
		vehicles = append(vehicles, walkNode(raw, baseURL)...)
	}

	return vehicles
}

// mapVehicleNode maps a JSON-LD Vehicle/Car node to VehicleRaw.
func mapVehicleNode(obj map[string]json.RawMessage, baseURL string) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{}

	v.VIN = coerceStringField(obj, "vehicleIdentificationNumber")
	if v.VIN == nil {
		v.VIN = coerceStringField(obj, "sku")
	}
	if v.VIN != nil {
		vin := normalize.NormalizeVIN(*v.VIN)
		if vin == "" {
			v.VIN = nil
		} else {
			v.VIN = &vin
		}
	}

	// Make: brand.name or manufacturer
	if brand, ok := obj["brand"]; ok {
		var brandObj map[string]json.RawMessage
		if err := json.Unmarshal(brand, &brandObj); err == nil {
			v.Make = coerceStringField(brandObj, "name")
		} else {
			v.Make = coerceString(brand)
		}
	}
	if v.Make == nil {
		v.Make = coerceStringField(obj, "manufacturer")
	}

	// Model: model or name (fallback)
	v.Model = coerceStringField(obj, "vehicleModel")
	if v.Model == nil {
		v.Model = coerceStringField(obj, "model")
	}
	if v.Model == nil {
		v.Model = coerceStringField(obj, "name")
	}

	// Year: vehicleModelDate (YYYY or YYYY-MM-DD)
	if s := coerceStringField(obj, "vehicleModelDate"); s != nil {
		yr := extractYear(*s)
		if yr > 0 {
			v.Year = &yr
		}
	}
	if v.Year == nil {
		if n := coerceIntField(obj, "vehicleModelDate"); n != nil {
			v.Year = n
		}
	}

	// Mileage: mileageFromOdometer
	if raw, ok := obj["mileageFromOdometer"]; ok {
		var qv quantitativeValue
		if err := json.Unmarshal(raw, &qv); err == nil && qv.Value != nil {
			n := int(*qv.Value)
			if qv.UnitCode == "SMI" { // miles → km
				n = int(float64(n) * 1.60934)
			}
			v.Mileage = &n
		} else {
			// Try as plain number
			v.Mileage = coerceIntField(obj, "mileageFromOdometer")
		}
	}

	// Fuel type
	if s := coerceStringField(obj, "fuelType"); s != nil {
		ft := normalize.NormalizeFuelType(*s)
		v.FuelType = &ft
	}

	// Transmission
	if s := coerceStringField(obj, "vehicleTransmission"); s != nil {
		tr := normalize.NormalizeTransmission(*s)
		v.Transmission = &tr
	}

	// Power (vehicleEngine.enginePower.value kW)
	if raw, ok := obj["vehicleEngine"]; ok {
		var engineObj map[string]json.RawMessage
		if err := json.Unmarshal(raw, &engineObj); err == nil {
			if raw2, ok2 := engineObj["enginePower"]; ok2 {
				var qv quantitativeValue
				if err2 := json.Unmarshal(raw2, &qv); err2 == nil && qv.Value != nil {
					kw := int(*qv.Value)
					v.PowerKW = &kw
				}
			}
		}
	}

	// Body type
	if s := coerceStringField(obj, "bodyType"); s != nil {
		bt := normalize.NormalizeBodyType(*s)
		v.BodyType = &bt
	}

	// Color
	v.Color = coerceStringField(obj, "color")

	// Doors, seats
	v.Doors = coerceIntField(obj, "numberOfDoors")
	v.Seats = coerceIntField(obj, "seatingCapacity")

	// Price: offers.price / offers.priceSpecification
	if raw, ok := obj["offers"]; ok {
		var offerObj map[string]json.RawMessage
		if err := json.Unmarshal(raw, &offerObj); err == nil {
			mapOfferToVehicle(offerObj, v)
		}
	}

	// Source URL
	if s := coerceStringField(obj, "url"); s != nil {
		v.SourceURL = normalize.CanonicalizePhotoURL(*s, baseURL)
	}
	if v.SourceURL == "" {
		if s := coerceStringField(obj, "@id"); s != nil {
			resolved := normalize.CanonicalizePhotoURL(*s, baseURL)
			if strings.HasPrefix(resolved, "http") {
				v.SourceURL = resolved
			}
		}
	}

	// Images
	v.ImageURLs = extractImages(obj, baseURL)

	// Listing ID (sku or @id fragment)
	if v.VIN != nil {
		v.SourceListingID = *v.VIN
	} else if s := coerceStringField(obj, "sku"); s != nil {
		v.SourceListingID = *s
	}

	return v
}

// mapOfferToVehicle extracts price information from an offers object.
func mapOfferToVehicle(offerObj map[string]json.RawMessage, v *pipeline.VehicleRaw) {
	// Price (may be string "28500" or number 28500 or "28.500,00 €")
	if raw, ok := offerObj["price"]; ok {
		if p := parsePrice(raw); p > 0 {
			v.PriceGross = &p
		}
	}

	// Currency
	v.Currency = coerceStringField(offerObj, "priceCurrency")
	if v.Currency != nil {
		c := normalize.NormalizeCurrency(*v.Currency)
		v.Currency = &c
	}

	// VAT mode from priceSpecification
	if raw, ok := offerObj["priceSpecification"]; ok {
		var spec map[string]json.RawMessage
		if err := json.Unmarshal(raw, &spec); err == nil {
			if s := coerceStringField(spec, "valueAddedTaxIncluded"); s != nil {
				vm := "gross"
				if *s == "false" {
					vm = "net"
				}
				v.VATMode = &vm
			}
		}
	}
}

// extractImages collects all image URLs from an object, resolving them to absolute.
func extractImages(obj map[string]json.RawMessage, baseURL string) []string {
	rawImg, ok := obj["image"]
	if !ok {
		return nil
	}

	var urls []string

	// Try string.
	if s := coerceString(rawImg); s != nil {
		urls = append(urls, normalize.CanonicalizePhotoURL(*s, baseURL))
	} else {
		// Try array.
		var arr []json.RawMessage
		if err := json.Unmarshal(rawImg, &arr); err == nil {
			for _, item := range arr {
				if s := coerceString(item); s != nil {
					urls = append(urls, normalize.CanonicalizePhotoURL(*s, baseURL))
				} else {
					// ImageObject.
					var imgObj map[string]json.RawMessage
					if err2 := json.Unmarshal(item, &imgObj); err2 == nil {
						if s2 := coerceStringField(imgObj, "contentUrl"); s2 != nil {
							urls = append(urls, normalize.CanonicalizePhotoURL(*s2, baseURL))
						} else if s2 := coerceStringField(imgObj, "url"); s2 != nil {
							urls = append(urls, normalize.CanonicalizePhotoURL(*s2, baseURL))
						}
					}
				}
			}
		} else {
			// Single ImageObject.
			var imgObj map[string]json.RawMessage
			if err2 := json.Unmarshal(rawImg, &imgObj); err2 == nil {
				if s := coerceStringField(imgObj, "contentUrl"); s != nil {
					urls = append(urls, normalize.CanonicalizePhotoURL(*s, baseURL))
				} else if s := coerceStringField(imgObj, "url"); s != nil {
					urls = append(urls, normalize.CanonicalizePhotoURL(*s, baseURL))
				}
			}
		}
	}

	return normalize.FilterPhotoURLs(normalize.DedupePhotoURLs(urls))
}

// -- JSON coercion helpers -------------------------------------------------------

type quantitativeValue struct {
	Type     string   `json:"@type"`
	Value    *float64 `json:"value"`
	UnitCode string   `json:"unitCode"`
}

func extractType(obj map[string]json.RawMessage) string {
	raw, ok := obj["@type"]
	if !ok {
		return ""
	}
	// @type may be a string or []string.
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return s
	}
	var arr []string
	if err := json.Unmarshal(raw, &arr); err == nil && len(arr) > 0 {
		return arr[0]
	}
	return ""
}

func coerceStringField(obj map[string]json.RawMessage, key string) *string {
	raw, ok := obj[key]
	if !ok {
		return nil
	}
	return coerceString(raw)
}

func coerceString(raw json.RawMessage) *string {
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		s = strings.TrimSpace(s)
		if s == "" {
			return nil
		}
		return &s
	}
	return nil
}

func coerceIntField(obj map[string]json.RawMessage, key string) *int {
	raw, ok := obj[key]
	if !ok {
		return nil
	}
	var f float64
	if err := json.Unmarshal(raw, &f); err == nil {
		n := int(f)
		return &n
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		var f2 float64
		if _, err2 := fmt.Sscanf(s, "%f", &f2); err2 == nil {
			n := int(f2)
			return &n
		}
	}
	return nil
}

func parsePrice(raw json.RawMessage) float64 {
	var f float64
	if err := json.Unmarshal(raw, &f); err == nil {
		return f
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		// Strip currency symbols, thousands separators (., space), keep decimal comma.
		s = strings.Map(func(r rune) rune {
			switch r {
			case '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.', ',':
				return r
			}
			return -1
		}, s)
		// European format: 28.500,00 → 28500.00
		if idx := strings.LastIndex(s, ","); idx >= 0 {
			s = strings.ReplaceAll(s[:idx], ".", "") + "." + s[idx+1:]
		}
		var p float64
		if _, err2 := fmt.Sscanf(s, "%f", &p); err2 == nil {
			return p
		}
	}
	return 0
}

func extractYear(s string) int {
	// Accept "2021", "2021-01-01", "2021-01", etc.
	if len(s) >= 4 {
		var yr int
		fmt.Sscanf(s[:4], "%d", &yr)
		if yr >= 1900 && yr <= 2100 {
			return yr
		}
	}
	return 0
}

func derefStr(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// resolveURL makes a URL absolute relative to base.
func resolveURL(rawURL, base string) string {
	if rawURL == "" {
		return ""
	}
	if strings.HasPrefix(rawURL, "http://") || strings.HasPrefix(rawURL, "https://") {
		return rawURL
	}
	b, err := url.Parse(base)
	if err != nil {
		return rawURL
	}
	r, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	return b.ResolveReference(r).String()
}

var _ = resolveURL // used indirectly via normalize.CanonicalizePhotoURL
