// Package e02_cms_rest implements extraction strategy E02 — CMS REST endpoint.
//
// # Strategy
//
// WordPress, Joomla and other CMS platforms expose public REST APIs for
// vehicle inventory management plugins. E02 enumerates known endpoint patterns
// for detected plugins, falls back to automatic endpoint discovery via the
// WP REST API index (/wp-json/), and paginates through results.
//
// # Applicable
//
// E02 is attempted when:
//   - CMSDetected contains "wordpress" AND ExtractionHints contains a known
//     vehicle plugin fingerprint, OR
//   - PlatformType is "CMS_WORDPRESS" (broad applicability for WP dealers)
//
// # Plugin endpoint registry
//
//   WP Car Manager          /wp-json/wp-car-manager/v1/vehicles
//   Car Dealer Plugin       /wp-json/car-dealer/v1/cars
//   Vehicle Manager         /wp-json/vehicle-manager/v1/listings
//   DealerPress             /wp-json/dealerpress/v1/inventory
//   Motors Theme CPT        /wp-json/wp/v2/listing?listing_type=car
//   Generic WP CPT          /wp-json/wp/v2/vehicle  /wp-json/wp/v2/car  /wp-json/wp/v2/listing
//   Auto Parts              /wp-json/auto-parts/v1/vehicles
//   JomListing (Joomla)     /index.php?option=com_jomlisting&view=listing&format=json
//
// # Rate limits
//
// 1 s between pages of the same dealer.
package e02_cms_rest

import (
	"context"
	"encoding/json"
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
	strategyID   = "E02"
	strategyName = "CMS REST endpoint"
	maxBodyBytes = 4 << 20 // 4 MiB
	maxPages     = 50      // WP REST API max pagination depth
	perPage      = 100     // WP REST API per_page maximum
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// endpointPattern maps a plugin hint keyword to a list of REST endpoint paths.
var endpointPattern = []struct {
	hint      string // ExtractionHint keyword that activates this pattern
	endpoints []string
}{
	{"wp-car-manager", []string{"/wp-json/wp-car-manager/v1/vehicles"}},
	{"car-dealer", []string{"/wp-json/car-dealer/v1/cars"}},
	{"vehicle-manager", []string{"/wp-json/vehicle-manager/v1/listings"}},
	{"dealerpress", []string{"/wp-json/dealerpress/v1/inventory"}},
	{"motors", []string{
		"/wp-json/wp/v2/listing?listing_type=car&per_page=100",
		"/wp-json/wp/v2/listing?per_page=100",
	}},
	{"auto-parts", []string{"/wp-json/auto-parts/v1/vehicles"}},
	// Generic WP CPT endpoints — always tried for any WP dealer.
	{"cms:wordpress", []string{
		"/wp-json/wp/v2/vehicle?per_page=100",
		"/wp-json/wp/v2/car?per_page=100",
		"/wp-json/wp/v2/listing?per_page=100",
		"/wp-json/wp/v2/auto?per_page=100",
	}},
	// Joomla vehicle plugins.
	{"cms:joomla", []string{
		"/index.php?option=com_jomlisting&view=listing&format=json",
		"/index.php?option=com_vehiclesforsale&task=getlist&format=json",
	}},
}

// CMSREST is the E02 extraction strategy.
type CMSREST struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a CMSREST strategy with default HTTP client.
func New() *CMSREST {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 1000)
}

// NewWithClient constructs a CMSREST strategy with a custom HTTP client and
// rate limit. Used in tests.
func NewWithClient(c *http.Client, rateLimitMs int) *CMSREST {
	return &CMSREST{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

// ID returns "E02".
func (e *CMSREST) ID() string { return strategyID }

// Name returns the human-readable strategy name.
func (e *CMSREST) Name() string { return strategyName }

// Priority returns 1100.
func (e *CMSREST) Priority() int { return pipeline.PriorityE02 }

// Applicable returns true for WordPress or Joomla dealers.
func (e *CMSREST) Applicable(dealer pipeline.Dealer) bool {
	cms := strings.ToLower(dealer.CMSDetected)
	if strings.Contains(cms, "wordpress") || strings.Contains(cms, "joomla") {
		return true
	}
	pt := strings.ToLower(dealer.PlatformType)
	if strings.Contains(pt, "wordpress") || strings.Contains(pt, "joomla") {
		return true
	}
	for _, hint := range dealer.ExtractionHints {
		if hint == "cms:wordpress" || hint == "cms:joomla" {
			return true
		}
	}
	return false
}

// Extract tries known REST endpoints and auto-discovery for the dealer.
func (e *CMSREST) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// Build the list of endpoint paths to try, based on hints.
	endpoints := e.selectEndpoints(dealer)

	// Also run WP auto-discovery (/wp-json/ index) for WP dealers.
	if e.isWordPress(dealer) {
		discovered := e.discoverWPEndpoints(ctx, baseURL)
		endpoints = mergePaths(endpoints, discovered)
	}

	tried := map[string]bool{}
	for _, path := range endpoints {
		if ctx.Err() != nil {
			break
		}
		if tried[path] {
			continue
		}
		tried[path] = true

		vehicles, pagesConsumed, err := e.fetchPaginated(ctx, baseURL, path)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "FETCH_ERROR",
				Message: err.Error(),
				URL:     baseURL + path,
			})
			continue
		}
		result.SourceCount += pagesConsumed
		result.Vehicles = append(result.Vehicles, vehicles...)

		if len(result.Vehicles) > 0 {
			// Found vehicles on this endpoint — record it as source URL.
			if result.SourceURL == "" {
				result.SourceURL = baseURL + path
			}
			break // stop trying further endpoints
		}
	}

	return result, nil
}

// selectEndpoints returns the REST paths to probe based on the dealer's hints.
func (e *CMSREST) selectEndpoints(dealer pipeline.Dealer) []string {
	hintSet := make(map[string]bool, len(dealer.ExtractionHints))
	for _, h := range dealer.ExtractionHints {
		hintSet[strings.ToLower(h)] = true
	}
	if strings.Contains(strings.ToLower(dealer.CMSDetected), "wordpress") {
		hintSet["cms:wordpress"] = true
	}
	if strings.Contains(strings.ToLower(dealer.CMSDetected), "joomla") {
		hintSet["cms:joomla"] = true
	}
	if strings.Contains(strings.ToLower(dealer.PlatformType), "wordpress") {
		hintSet["cms:wordpress"] = true
	}

	seen := map[string]bool{}
	var paths []string
	for _, pat := range endpointPattern {
		if hintSet[pat.hint] {
			for _, ep := range pat.endpoints {
				if !seen[ep] {
					seen[ep] = true
					paths = append(paths, ep)
				}
			}
		}
	}
	return paths
}

// isWordPress returns true if the dealer is identified as WordPress.
func (e *CMSREST) isWordPress(dealer pipeline.Dealer) bool {
	if strings.Contains(strings.ToLower(dealer.CMSDetected), "wordpress") {
		return true
	}
	for _, h := range dealer.ExtractionHints {
		if h == "cms:wordpress" {
			return true
		}
	}
	return strings.Contains(strings.ToLower(dealer.PlatformType), "wordpress")
}

// discoverWPEndpoints fetches /wp-json/ and extracts namespace paths that
// contain vehicle/car/dealer/inventory/listing/auto keywords.
func (e *CMSREST) discoverWPEndpoints(ctx context.Context, baseURL string) []string {
	url := baseURL + "/wp-json/"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
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

	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return nil
	}

	var index struct {
		Namespaces []string `json:"namespaces"`
		Routes     map[string]struct {
			Namespace string `json:"namespace"`
		} `json:"routes"`
	}
	if err := json.Unmarshal(body, &index); err != nil {
		return nil
	}

	vehicleKeywords := []string{"vehicle", "car", "dealer", "inventory", "listing", "auto", "moto"}

	var paths []string
	for _, ns := range index.Namespaces {
		nsLow := strings.ToLower(ns)
		for _, kw := range vehicleKeywords {
			if strings.Contains(nsLow, kw) {
				paths = append(paths, "/wp-json/"+ns+"/vehicles?per_page=100")
				paths = append(paths, "/wp-json/"+ns+"/cars?per_page=100")
				paths = append(paths, "/wp-json/"+ns+"/listings?per_page=100")
				break
			}
		}
	}
	return paths
}

// fetchPaginated fetches all pages for a single endpoint, handling WP REST API
// pagination via X-WP-TotalPages header and Link: rel="next".
// Returns all extracted vehicles and the number of pages fetched.
func (e *CMSREST) fetchPaginated(ctx context.Context, baseURL, path string) ([]*pipeline.VehicleRaw, int, error) {
	var vehicles []*pipeline.VehicleRaw
	currentPath := path
	pages := 0

	for pages < maxPages {
		if ctx.Err() != nil {
			break
		}
		if pages > 0 {
			sleep := e.rateLimitMs
			if sleep <= 0 {
				sleep = 50
			}
			select {
			case <-ctx.Done():
				return vehicles, pages, nil
			case <-time.After(time.Duration(sleep) * time.Millisecond):
			}
		}

		pageVehicles, totalPages, nextPath, err := e.fetchOnePage(ctx, baseURL, currentPath)
		if err != nil {
			if pages == 0 {
				return nil, 0, err // first page failure is an error
			}
			break // subsequent page failures stop pagination silently
		}
		pages++
		vehicles = append(vehicles, pageVehicles...)

		// Determine next page.
		if nextPath != "" {
			currentPath = nextPath
			continue
		}
		if totalPages > pages {
			// Append &page=N to current path.
			if strings.Contains(currentPath, "page=") {
				currentPath = replacePage(currentPath, pages+1)
			} else {
				sep := "&"
				if !strings.Contains(currentPath, "?") {
					sep = "?"
				}
				currentPath = currentPath + sep + "page=" + strconv.Itoa(pages+1)
			}
			continue
		}
		break // all pages consumed
	}
	return vehicles, pages, nil
}

// fetchOnePage fetches a single REST API page and returns extracted vehicles,
// total pages from header, next page path from Link header, and error.
func (e *CMSREST) fetchOnePage(ctx context.Context, baseURL, path string) ([]*pipeline.VehicleRaw, int, string, error) {
	url := baseURL + path
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, 0, "", err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, 0, "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, 0, "", nil // 404 = endpoint doesn't exist, non-fatal
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, 0, "", fmt.Errorf("HTTP 429: %s", url)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, 0, "", fmt.Errorf("HTTP %d: %s", resp.StatusCode, url)
	}

	// Extract pagination headers.
	totalPages := 1
	if raw := resp.Header.Get("X-WP-TotalPages"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 1 {
			totalPages = n
		}
	}
	nextPath := extractNextLink(resp.Header.Get("Link"), baseURL)

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, 0, "", fmt.Errorf("read body: %w", err)
	}

	vehicles := parseWPResponse(body, baseURL)
	return vehicles, totalPages, nextPath, nil
}

// extractNextLink parses the WP REST API Link header to extract the rel="next"
// URL, returning the path portion relative to baseURL.
func extractNextLink(linkHeader, baseURL string) string {
	if linkHeader == "" {
		return ""
	}
	for _, part := range strings.Split(linkHeader, ",") {
		part = strings.TrimSpace(part)
		if strings.Contains(part, `rel="next"`) {
			if start := strings.Index(part, "<"); start >= 0 {
				if end := strings.Index(part[start:], ">"); end >= 0 {
					fullURL := part[start+1 : start+end]
					if strings.HasPrefix(fullURL, baseURL) {
						return fullURL[len(baseURL):]
					}
					return fullURL
				}
			}
		}
	}
	return ""
}

// replacePage replaces the page= parameter value in a URL path.
func replacePage(path string, page int) string {
	if idx := strings.Index(path, "page="); idx >= 0 {
		rest := path[idx+5:]
		end := strings.IndexByte(rest, '&')
		if end < 0 {
			end = len(rest)
		}
		return path[:idx+5] + strconv.Itoa(page) + rest[end:]
	}
	return path
}

// mergePaths appends items from b to a, skipping duplicates.
func mergePaths(a, b []string) []string {
	seen := make(map[string]bool, len(a))
	for _, v := range a {
		seen[v] = true
	}
	for _, v := range b {
		if !seen[v] {
			seen[v] = true
			a = append(a, v)
		}
	}
	return a
}

// -- WP REST API response parsing -----------------------------------------------

// wpPost represents a minimal WP REST API post response.
type wpPost struct {
	ID     int    `json:"id"`
	Link   string `json:"link"`
	Title  struct {
		Rendered string `json:"rendered"`
	} `json:"title"`
	// Meta fields (WP Car Manager, etc.)
	Meta           map[string]interface{}  `json:"meta"`
	ACF            map[string]interface{}  `json:"acf"`
	// Plugin-specific top-level fields
	VehicleMake    string  `json:"vehicle_make"`
	VehicleModel   string  `json:"vehicle_model"`
	VehicleYear    int     `json:"vehicle_year"`
	VehicleMileage int     `json:"vehicle_mileage"`
	VehiclePrice   float64 `json:"vehicle_price"`
	VehicleFuel    string  `json:"vehicle_fuel_type"`
	VehicleTrans   string  `json:"vehicle_transmission"`
	VehicleVIN     string  `json:"vehicle_vin"`
	// Images
	FeaturedMedia  int    `json:"featured_media"`
	Images         []string `json:"vehicle_images"`
}

// parseWPResponse parses a WP REST API JSON array into VehicleRaw records.
func parseWPResponse(body []byte, baseURL string) []*pipeline.VehicleRaw {
	var posts []wpPost
	if err := json.Unmarshal(body, &posts); err != nil {
		// Try single object.
		var p wpPost
		if err2 := json.Unmarshal(body, &p); err2 == nil {
			posts = []wpPost{p}
		} else {
			return nil
		}
	}

	vehicles := make([]*pipeline.VehicleRaw, 0, len(posts))
	for _, post := range posts {
		v := mapWPPost(post, baseURL)
		if v != nil {
			vehicles = append(vehicles, v)
		}
	}
	return vehicles
}

// mapWPPost converts a wpPost to a VehicleRaw.
// It tries top-level fields, then Meta (WP Car Manager style), then ACF fields.
func mapWPPost(post wpPost, baseURL string) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{}

	// Source URL and listing ID.
	v.SourceURL = post.Link
	if v.SourceURL == "" && post.ID > 0 {
		v.SourceURL = fmt.Sprintf("%s/?p=%d", baseURL, post.ID)
	}
	v.SourceListingID = strconv.Itoa(post.ID)

	// Try top-level fields first (some plugins put them at root).
	if post.VehicleMake != "" {
		mk := post.VehicleMake
		v.Make = &mk
	}
	if post.VehicleModel != "" {
		m := post.VehicleModel
		v.Model = &m
	}
	if post.VehicleYear > 0 {
		y := post.VehicleYear
		v.Year = &y
	}
	if post.VehicleMileage > 0 {
		km := post.VehicleMileage
		v.Mileage = &km
	}
	if post.VehiclePrice > 0 {
		p := post.VehiclePrice
		v.PriceGross = &p
	}
	if post.VehicleFuel != "" {
		ft := normalize.NormalizeFuelType(post.VehicleFuel)
		v.FuelType = &ft
	}
	if post.VehicleTrans != "" {
		tr := normalize.NormalizeTransmission(post.VehicleTrans)
		v.Transmission = &tr
	}
	if post.VehicleVIN != "" {
		vin := normalize.NormalizeVIN(post.VehicleVIN)
		if vin != "" {
			v.VIN = &vin
		}
	}
	for _, imgURL := range post.Images {
		if url := normalize.CanonicalizePhotoURL(imgURL, baseURL); url != "" {
			v.ImageURLs = append(v.ImageURLs, url)
		}
	}

	// Try meta fields (WP Car Manager, vehicle-manager style).
	if post.Meta != nil {
		applyMetaFields(post.Meta, v, baseURL)
	}

	// Try ACF fields (Advanced Custom Fields).
	if post.ACF != nil {
		applyMetaFields(post.ACF, v, baseURL)
	}

	// Nothing useful extracted — skip.
	if v.Make == nil && v.Model == nil {
		return nil
	}

	return v
}

// applyMetaFields populates VehicleRaw from a meta/ACF map.
func applyMetaFields(meta map[string]interface{}, v *pipeline.VehicleRaw, baseURL string) {
	get := func(key string) string {
		if val, ok := meta[key]; ok {
			switch t := val.(type) {
			case string:
				return strings.TrimSpace(t)
			case float64:
				return strconv.FormatFloat(t, 'f', -1, 64)
			}
		}
		return ""
	}
	getFloat := func(key string) float64 {
		if val, ok := meta[key]; ok {
			switch t := val.(type) {
			case float64:
				return t
			case string:
				var f float64
				fmt.Sscanf(t, "%f", &f)
				return f
			}
		}
		return 0
	}

	// Known meta key patterns (WP Car Manager uses "vehicle_make", etc.)
	for _, key := range []string{"vehicle_make", "make", "_make", "car_make"} {
		if s := get(key); s != "" && v.Make == nil {
			mk := s
			v.Make = &mk
			break
		}
	}
	for _, key := range []string{"vehicle_model", "model", "_model", "car_model"} {
		if s := get(key); s != "" && v.Model == nil {
			m := s
			v.Model = &m
			break
		}
	}
	for _, key := range []string{"vehicle_year", "year", "_year", "car_year"} {
		if f := getFloat(key); f > 0 && v.Year == nil {
			yr := int(f)
			v.Year = &yr
			break
		}
	}
	for _, key := range []string{"vehicle_mileage", "mileage", "_mileage", "odometer"} {
		if f := getFloat(key); f > 0 && v.Mileage == nil {
			km := int(f)
			v.Mileage = &km
			break
		}
	}
	for _, key := range []string{"vehicle_price", "price", "_price", "car_price"} {
		if f := getFloat(key); f > 0 && v.PriceGross == nil {
			p := f
			v.PriceGross = &p
			break
		}
	}
	for _, key := range []string{"vehicle_fuel_type", "fuel_type", "fuel", "_fuel"} {
		if s := get(key); s != "" && v.FuelType == nil {
			ft := normalize.NormalizeFuelType(s)
			v.FuelType = &ft
			break
		}
	}
	for _, key := range []string{"vehicle_transmission", "transmission", "_transmission"} {
		if s := get(key); s != "" && v.Transmission == nil {
			tr := normalize.NormalizeTransmission(s)
			v.Transmission = &tr
			break
		}
	}
	for _, key := range []string{"vehicle_vin", "vin", "_vin"} {
		if s := get(key); s != "" && v.VIN == nil {
			vin := normalize.NormalizeVIN(s)
			if vin != "" {
				v.VIN = &vin
			}
			break
		}
	}

	// Images in meta (array of URLs).
	for _, key := range []string{"vehicle_images", "images", "_images", "gallery"} {
		if val, ok := meta[key]; ok {
			switch t := val.(type) {
			case []interface{}:
				for _, item := range t {
					if s, ok2 := item.(string); ok2 {
						if url := normalize.CanonicalizePhotoURL(s, baseURL); url != "" {
							v.ImageURLs = append(v.ImageURLs, url)
						}
					}
				}
			case string:
				if url := normalize.CanonicalizePhotoURL(t, baseURL); url != "" {
					v.ImageURLs = append(v.ImageURLs, url)
				}
			}
			if len(v.ImageURLs) > 0 {
				break
			}
		}
	}

	v.ImageURLs = normalize.DedupePhotoURLs(v.ImageURLs)
}
