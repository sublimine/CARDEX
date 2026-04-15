// Package e03_sitemap implements extraction strategy E03 — Sitemap XML.
//
// # Strategy
//
// Most web servers publish a sitemap.xml advertising the URLs they want indexed.
// Dealers often publish a dedicated vehicle sitemap (e.g. /sitemap-vehicles.xml)
// listing every individual listing page. E03 walks this sitemap, filters vehicle
// URLs by path pattern, fetches each listing page, and extracts vehicle data.
//
// # Sitemap formats handled
//
//   - Sitemap Index (sitemapindex): top-level file listing sub-sitemaps; E03 follows
//     up to maxSubSitemaps child sitemaps, filtering for vehicle-named ones first.
//   - URL set (urlset): flat list of <url> elements; filtered by vehiclePathPatterns.
//
// # Discovery
//
//  1. Parse robots.txt for "Sitemap:" directives.
//  2. Probe common sitemap paths (/sitemap.xml, /sitemap-vehicles.xml, etc.).
//
// # Vehicle URL filtering
//
// URL paths are matched against vehicle path patterns:
// /vehicle/, /auto/, /car/, /voiture/, /coche/, /wagen/, /fahrzeug/,
// /used-cars/, /inventory/, /listing/, /annonce/, /occasion/
//
// # Per-page extraction
//
//  1. Fetch HTML, extract JSON-LD Vehicle blocks (via e01_jsonld.ParseVehiclesFromHTML).
//  2. Fallback: Open Graph meta tags for title/price.
//  3. Fallback: heuristic price/year/mileage regex from page title.
//
// # Rate limits
//
// 1 s between individual vehicle page fetches.
// Sitemap XML files themselves: no sleep (low-cost static XML).
package e03_sitemap

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/extraction/internal/extractor/e01_jsonld"
	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID    = "E03"
	strategyName  = "Sitemap XML"
	maxBodyBytes  = 4 << 20  // 4 MiB
	maxSubSitemaps = 10      // max child sitemaps from a sitemapindex
	maxVehicleURLs = 500     // max vehicle pages fetched per run
	cardexUA      = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// sitemapPaths are the candidate sitemap paths probed if robots.txt has no Sitemap directive.
var sitemapPaths = []string{
	"/sitemap.xml",
	"/sitemap_index.xml",
	"/sitemap-vehicles.xml",
	"/sitemap-cars.xml",
	"/sitemap-inventory.xml",
	"/sitemap-fahrzeuge.xml",
	"/sitemap-voitures.xml",
	"/sitemap-coches.xml",
	"/sitemap-occasions.xml",
	"/sitemap-listings.xml",
	"/sitemap-posts.xml", // WP fallback: vehicle CPT often in posts sitemap
}

// vehiclePathPatterns match URL path fragments that indicate a vehicle listing.
var vehiclePathPatterns = []string{
	"/vehicle/", "/vehicles/",
	"/auto/", "/autos/",
	"/car/", "/cars/",
	"/voiture/", "/voitures/",
	"/coche/", "/coches/",
	"/wagen/", "/fahrzeug/", "/fahrzeuge/",
	"/used-cars/", "/used-car/",
	"/inventory/",
	"/listing/", "/listings/",
	"/annonce/", "/annonces/",
	"/occasion/", "/occasions/",
	"/gebrauchtwagen/",
	"/auto-usato/", "/auto-usati/",
}

// -- XML structs for sitemap parsing ------------------------------------------

type sitemapIndex struct {
	XMLName  xml.Name       `xml:"sitemapindex"`
	Sitemaps []sitemapEntry `xml:"sitemap"`
}

type sitemapEntry struct {
	Loc     string `xml:"loc"`
	Lastmod string `xml:"lastmod"`
}

type urlSet struct {
	XMLName xml.Name   `xml:"urlset"`
	URLs    []urlEntry `xml:"url"`
}

type urlEntry struct {
	Loc        string  `xml:"loc"`
	Lastmod    string  `xml:"lastmod"`
	Changefreq string  `xml:"changefreq"`
	Priority   float64 `xml:"priority"`
}

// Sitemap is the E03 extraction strategy.
type Sitemap struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a Sitemap strategy with default HTTP client.
func New() *Sitemap {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 1000)
}

// NewWithClient constructs a Sitemap strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *Sitemap {
	return &Sitemap{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

// ID returns "E03".
func (e *Sitemap) ID() string { return strategyID }

// Name returns the human-readable strategy name.
func (e *Sitemap) Name() string { return strategyName }

// Priority returns 1000.
func (e *Sitemap) Priority() int { return pipeline.PriorityE03 }

// Applicable returns true for all dealers — any site may publish a sitemap.
func (e *Sitemap) Applicable(_ pipeline.Dealer) bool { return true }

// Extract discovers the dealer sitemap, filters vehicle URLs, and extracts data.
func (e *Sitemap) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// 1. Discover sitemap URL(s).
	sitemapURLs := e.discoverSitemaps(ctx, baseURL)
	if len(sitemapURLs) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_SITEMAP",
			Message: "no sitemap found via robots.txt or probe paths",
			URL:     baseURL,
		})
		return result, nil
	}

	// 2. Collect vehicle URLs from all discovered sitemaps.
	vehicleURLs := e.collectVehicleURLs(ctx, sitemapURLs, baseURL)
	if len(vehicleURLs) == 0 {
		return result, nil
	}
	if len(vehicleURLs) > maxVehicleURLs {
		vehicleURLs = vehicleURLs[:maxVehicleURLs]
	}

	result.SourceURL = sitemapURLs[0]
	seenVehicles := map[string]bool{}

	// 3. Fetch and extract each vehicle page.
	for i, pageURL := range vehicleURLs {
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

		vehicles, err := e.fetchVehiclePage(ctx, pageURL, baseURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "PAGE_FETCH_ERROR",
				Message: err.Error(),
				URL:     pageURL,
			})
			continue
		}
		result.SourceCount++

		for _, v := range vehicles {
			key := vehicleKey(v)
			if !seenVehicles[key] {
				seenVehicles[key] = true
				result.Vehicles = append(result.Vehicles, v)
			}
		}
	}

	return result, nil
}

// discoverSitemaps returns sitemap URLs found in robots.txt and common paths.
func (e *Sitemap) discoverSitemaps(ctx context.Context, baseURL string) []string {
	var urls []string

	// Parse robots.txt for Sitemap: directives.
	robotsURLs := e.parsRobotsTxt(ctx, baseURL)
	urls = append(urls, robotsURLs...)

	if len(urls) > 0 {
		return urls
	}

	// Probe common paths.
	for _, path := range sitemapPaths {
		if ctx.Err() != nil {
			break
		}
		u := baseURL + path
		if e.probeURL(ctx, u) {
			urls = append(urls, u)
			break // found one — use it
		}
	}
	return urls
}

// parsRobotsTxt fetches and parses robots.txt for Sitemap: directives.
func (e *Sitemap) parsRobotsTxt(ctx context.Context, baseURL string) []string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/robots.txt", nil)
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

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	var sitemaps []string
	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(strings.ToLower(line), "sitemap:") {
			u := strings.TrimSpace(line[len("sitemap:"):])
			if u != "" {
				sitemaps = append(sitemaps, u)
			}
		}
	}
	return sitemaps
}

// probeURL returns true if the URL returns HTTP 200.
func (e *Sitemap) probeURL(ctx context.Context, u string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, u, nil)
	if err != nil {
		return false
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := e.client.Do(req)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// collectVehicleURLs fetches sitemap URLs, resolves sub-sitemaps, and returns
// vehicle-matching URLs.
func (e *Sitemap) collectVehicleURLs(ctx context.Context, sitemapURLs []string, baseURL string) []string {
	var vehicleURLs []string
	processedSitemaps := map[string]bool{}

	var processSitemap func(u string, depth int)
	processSitemap = func(u string, depth int) {
		if processedSitemaps[u] || depth > 2 || ctx.Err() != nil {
			return
		}
		processedSitemaps[u] = true

		body, err := e.fetchXML(ctx, u)
		if err != nil {
			return
		}

		// Try sitemapindex first.
		var idx sitemapIndex
		if err := xml.Unmarshal(body, &idx); err == nil && len(idx.Sitemaps) > 0 {
			// Prioritise vehicle-named sub-sitemaps.
			prioritised := filterVehicleSitemaps(idx.Sitemaps)
			others := idx.Sitemaps

			processed := 0
			for _, sm := range prioritised {
				if processed >= maxSubSitemaps || ctx.Err() != nil {
					break
				}
				processSitemap(sm.Loc, depth+1)
				processed++
			}
			if len(vehicleURLs) == 0 {
				for _, sm := range others {
					if processed >= maxSubSitemaps || ctx.Err() != nil {
						break
					}
					if !processedSitemaps[sm.Loc] {
						processSitemap(sm.Loc, depth+1)
						processed++
					}
				}
			}
			return
		}

		// Try urlset.
		var uset urlSet
		if err := xml.Unmarshal(body, &uset); err == nil {
			for _, u := range uset.URLs {
				if isVehicleURL(u.Loc) {
					vehicleURLs = append(vehicleURLs, u.Loc)
					if len(vehicleURLs) >= maxVehicleURLs {
						return
					}
				}
			}
		}
	}

	for _, u := range sitemapURLs {
		processSitemap(u, 0)
		if len(vehicleURLs) >= maxVehicleURLs {
			break
		}
	}
	return vehicleURLs
}

// filterVehicleSitemaps returns sub-sitemaps whose URL contains a vehicle keyword.
func filterVehicleSitemaps(sitemaps []sitemapEntry) []sitemapEntry {
	keywords := []string{"vehicle", "car", "auto", "fahrzeug", "voiture",
		"coche", "inventory", "listing", "occasion", "gebrauchtwagen"}
	var out []sitemapEntry
	for _, sm := range sitemaps {
		loc := strings.ToLower(sm.Loc)
		for _, kw := range keywords {
			if strings.Contains(loc, kw) {
				out = append(out, sm)
				break
			}
		}
	}
	return out
}

// isVehicleURL returns true if the URL path matches a vehicle listing pattern.
func isVehicleURL(u string) bool {
	lower := strings.ToLower(u)
	for _, pat := range vehiclePathPatterns {
		if strings.Contains(lower, pat) {
			return true
		}
	}
	return false
}

// fetchXML fetches a URL and returns the body bytes.
func (e *Sitemap) fetchXML(ctx context.Context, u string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/xml,text/xml,*/*")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", u)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, u)
	}
	return io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
}

// fetchVehiclePage fetches a vehicle listing page and extracts vehicle data.
// Priority: JSON-LD → Open Graph meta → heuristic title/meta.
func (e *Sitemap) fetchVehiclePage(ctx context.Context, pageURL, baseURL string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,*/*")

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

	// 1. Try JSON-LD (highest quality).
	vehicles, _ := e01_jsonld.ParseVehiclesFromHTML(body, baseURL)
	if len(vehicles) > 0 {
		// Override SourceURL to the canonical listing URL.
		for _, v := range vehicles {
			if v.SourceURL == "" {
				v.SourceURL = pageURL
			}
		}
		return vehicles, nil
	}

	// 2. Fallback: Open Graph + heuristic extraction.
	v := extractFromMetaAndHeuristics(body, pageURL, baseURL)
	if v != nil {
		return []*pipeline.VehicleRaw{v}, nil
	}

	return nil, nil
}

// extractFromMetaAndHeuristics extracts vehicle data from OG meta tags and
// heuristic patterns in page title/H1 when JSON-LD is absent.
func extractFromMetaAndHeuristics(html []byte, pageURL, baseURL string) *pipeline.VehicleRaw {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(html)))
	if err != nil {
		return nil
	}

	v := &pipeline.VehicleRaw{SourceURL: pageURL}

	// Open Graph title → parse for make/model/year.
	title := ""
	if og := doc.Find(`meta[property="og:title"]`).AttrOr("content", ""); og != "" {
		title = og
	}
	if title == "" {
		title = strings.TrimSpace(doc.Find("title").First().Text())
	}
	if title == "" {
		title = strings.TrimSpace(doc.Find("h1").First().Text())
	}

	if title != "" {
		parseVehicleTitle(title, v)
	}

	// Price from OG or meta[name="price"].
	priceStr := doc.Find(`meta[property="product:price:amount"]`).AttrOr("content", "")
	if priceStr == "" {
		priceStr = doc.Find(`meta[name="price"]`).AttrOr("content", "")
	}
	if priceStr != "" {
		if p := parseHeuristicPrice(priceStr); p > 0 {
			v.PriceGross = &p
		}
	}

	// Image from OG.
	if imgURL := doc.Find(`meta[property="og:image"]`).AttrOr("content", ""); imgURL != "" {
		canonical := normalize.CanonicalizePhotoURL(imgURL, baseURL)
		v.ImageURLs = append(v.ImageURLs, canonical)
	}

	if v.Make == nil && v.Model == nil {
		return nil // nothing useful
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
	return make_ + "|" + model
}

// -- Heuristic vehicle title parser -------------------------------------------

var (
	reYear    = regexp.MustCompile(`\b(19[89]\d|20[012]\d)\b`)
	reMileage = regexp.MustCompile(`(?i)\b(\d[\d\s.]*)\s*(km|kms|kilometre|kilometer)\b`)
	rePrice   = regexp.MustCompile(`(?i)(\d[\d\s.,]*)[\s]*(€|eur|euro)\b`)
	rePriceNum = regexp.MustCompile(`^\d[\d.,\s]*$`)
)

// Known automotive makes for heuristic detection.
var knownMakes = []string{
	"Abarth", "Alfa Romeo", "Audi", "BMW", "Citroen", "Citroën", "Cupra",
	"Dacia", "DS", "Ferrari", "Fiat", "Ford", "Honda", "Hyundai", "Infiniti",
	"Jaguar", "Jeep", "Kia", "Lamborghini", "Land Rover", "Lexus", "Maserati",
	"Mazda", "Mercedes", "Mercedes-Benz", "MINI", "Mini", "Mitsubishi",
	"Nissan", "Opel", "Peugeot", "Porsche", "Renault", "SEAT", "Seat", "Škoda",
	"Skoda", "Smart", "Subaru", "Suzuki", "Tesla", "Toyota", "Volkswagen",
	"Volvo", "VW",
}

func parseVehicleTitle(title string, v *pipeline.VehicleRaw) {
	// Year.
	if m := reYear.FindString(title); m != "" {
		yr, _ := strconv.Atoi(m)
		v.Year = &yr
	}

	// Mileage.
	if m := reMileage.FindStringSubmatch(title); len(m) >= 2 {
		raw := strings.Map(func(r rune) rune {
			if r >= '0' && r <= '9' {
				return r
			}
			return -1
		}, m[1])
		km, err := strconv.Atoi(raw)
		if err == nil && km > 0 {
			v.Mileage = &km
		}
	}

	// Price.
	if m := rePrice.FindStringSubmatch(title); len(m) >= 2 {
		if p := parseHeuristicPrice(m[1]); p > 0 {
			v.PriceGross = &p
		}
	}

	// Make.
	titleUpper := strings.ToUpper(title)
	for _, make_ := range knownMakes {
		if strings.Contains(titleUpper, strings.ToUpper(make_)) {
			mk := make_
			v.Make = &mk

			// Model: first word after make.
			idx := strings.Index(titleUpper, strings.ToUpper(make_))
			rest := strings.TrimSpace(title[idx+len(make_):])
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

// parseHeuristicPrice parses a price string like "28.500", "28500", "28 500,00".
func parseHeuristicPrice(s string) float64 {
	s = strings.TrimSpace(s)
	// Strip non-numeric except . and ,
	s = strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' || r == '.' || r == ',' {
			return r
		}
		return -1
	}, s)
	// European format: last , or . is decimal separator.
	// Heuristic: if contains comma after dot, it's European (28.500,00).
	if di := strings.LastIndex(s, ","); di >= 0 {
		s = strings.ReplaceAll(s[:di], ".", "") + "." + s[di+1:]
	}
	var p float64
	fmt.Sscanf(s, "%f", &p)
	return p
}
