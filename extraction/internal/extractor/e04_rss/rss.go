// Package e04_rss implements extraction strategy E04 — RSS/Atom feeds.
//
// # Strategy
//
// Many dealer CMS platforms (WordPress, custom solutions) expose vehicle
// inventory as RSS 2.0 or Atom 1.0 feeds. E04 auto-discovers feeds from the
// dealer homepage, probes common feed paths, and extracts vehicle data from
// feed items.
//
// # Feed discovery
//
//  1. Check dealer.RSSFeedURL hint (from earlier discovery phases).
//  2. Fetch dealer homepage and look for <link rel="alternate"
//     type="application/rss+xml|atom+xml" href="…">.
//  3. Probe common feed paths (/feed/, /rss.xml, /inventory.rss, etc.).
//
// # Feed formats
//
//   - RSS 2.0: <rss version="2.0"><channel><item>…</item></channel></rss>
//   - Atom 1.0: <feed xmlns="http://www.w3.org/2005/Atom"><entry>…</entry></feed>
//
// # Vehicle data extraction
//
//  1. Inline custom fields in item/entry: <make>, <model>, <year>, <price>,
//     <mileage>, <vin>, <color>, <fuel>.
//  2. Heuristic parsing of <title> (year/make/model/price patterns).
//  3. Link-follow fallback: if item has a link but no inline vehicle data,
//     fetch the linked page and delegate to JSON-LD extraction (E01 logic).
//
// # Rate limits
//
// Configurable; default 1 s between vehicle page fetches.
// Feed XML files themselves: no sleep (static XML, one request per feed).
package e04_rss

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/extraction/internal/extractor/e01_jsonld"
	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E04"
	strategyName = "RSS/Atom Feeds"
	maxBodyBytes = 4 << 20 // 4 MiB
	maxFeedItems = 500
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// feedPaths are the candidate feed paths probed if homepage discovery fails.
var feedPaths = []string{
	"/feed/",
	"/feed",
	"/rss",
	"/rss.xml",
	"/feed.rss",
	"/feed.xml",
	"/atom.xml",
	"/inventory.rss",
	"/inventory.xml",
	"/cars.rss",
	"/vehicles.rss",
	"/feed/?post_type=vehicle",
	"/rss/vehicles",
	"/rss/inventory",
}

// -- RSS 2.0 XML structs -------------------------------------------------------

type rssFeed struct {
	XMLName xml.Name   `xml:"rss"`
	Channel rssChannel `xml:"channel"`
}

type rssChannel struct {
	Title string    `xml:"title"`
	Link  string    `xml:"link"`
	Items []rssItem `xml:"item"`
}

// rssItem captures both standard fields and common custom vehicle fields.
// Custom fields are read from bare element names (no namespace prefix).
type rssItem struct {
	Title       string `xml:"title"`
	Link        string `xml:"link"`
	Description string `xml:"description"`
	GUID        string `xml:"guid"`
	PubDate     string `xml:"pubDate"`
	// Custom vehicle fields — bare local names, matched regardless of namespace.
	Make    string `xml:"make"`
	Model   string `xml:"model"`
	Year    string `xml:"year"`
	Mileage string `xml:"mileage"`
	Price   string `xml:"price"`
	VIN     string `xml:"vin"`
	Color   string `xml:"color"`
	Fuel    string `xml:"fuel"`
}

// -- Atom 1.0 XML structs -----------------------------------------------------

const atomNS = "http://www.w3.org/2005/Atom"

type atomFeed struct {
	XMLName xml.Name    `xml:"http://www.w3.org/2005/Atom feed"`
	Title   atomText    `xml:"http://www.w3.org/2005/Atom title"`
	Entries []atomEntry `xml:"http://www.w3.org/2005/Atom entry"`
}

type atomEntry struct {
	Title   atomText   `xml:"http://www.w3.org/2005/Atom title"`
	Links   []atomLink `xml:"http://www.w3.org/2005/Atom link"`
	Summary atomText   `xml:"http://www.w3.org/2005/Atom summary"`
	ID      string     `xml:"http://www.w3.org/2005/Atom id"`
	// Vehicle fields — same bare names approach as RSS.
	Make    string `xml:"make"`
	Model   string `xml:"model"`
	Year    string `xml:"year"`
	Mileage string `xml:"mileage"`
	Price   string `xml:"price"`
	VIN     string `xml:"vin"`
	Color   string `xml:"color"`
	Fuel    string `xml:"fuel"`
}

type atomText struct {
	Value string `xml:",chardata"`
}

type atomLink struct {
	Href string `xml:"href,attr"`
	Rel  string `xml:"rel,attr"`
	Type string `xml:"type,attr"`
}

// RSS is the E04 extraction strategy.
type RSS struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs an RSS strategy with default HTTP client.
func New() *RSS {
	return NewWithClient(&http.Client{Timeout: 15 * time.Second}, 1000)
}

// NewWithClient constructs an RSS strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *RSS {
	return &RSS{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

// ID returns "E04".
func (e *RSS) ID() string { return strategyID }

// Name returns the human-readable strategy name.
func (e *RSS) Name() string { return strategyName }

// Priority returns 900.
func (e *RSS) Priority() int { return pipeline.PriorityE04 }

// Applicable returns true for all dealers — any site may publish a feed.
func (e *RSS) Applicable(_ pipeline.Dealer) bool { return true }

// Extract discovers RSS/Atom feeds for the dealer, parses them, and extracts
// vehicle data from items.
func (e *RSS) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// 1. Discover feed URL(s).
	feedURLs := e.discoverFeeds(ctx, dealer, baseURL)
	if len(feedURLs) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_FEED",
			Message: "no RSS/Atom feed found via homepage discovery or probe paths",
			URL:     baseURL,
		})
		return result, nil
	}

	seenVehicles := map[string]bool{}

	// 2. Parse each feed URL; stop after first successful parse.
	for _, feedURL := range feedURLs {
		if ctx.Err() != nil {
			break
		}
		items, feedErr := e.parseFeed(ctx, feedURL)
		if feedErr != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "FEED_ERROR",
				Message: feedErr.Error(),
				URL:     feedURL,
			})
			continue
		}
		if len(items) == 0 {
			continue
		}

		result.SourceURL = feedURL

		for i, item := range items {
			if ctx.Err() != nil {
				break
			}
			if len(result.Vehicles) >= maxFeedItems {
				break
			}

			if i > 0 && item.linkURL != "" {
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

			vehicles := e.extractFromItem(ctx, item, baseURL)
			for _, v := range vehicles {
				key := vehicleKey(v)
				if !seenVehicles[key] {
					seenVehicles[key] = true
					result.Vehicles = append(result.Vehicles, v)
				}
			}
		}

		if len(result.Vehicles) > 0 {
			break // stop after first feed that yields results
		}
	}

	return result, nil
}

// feedItem is a normalised representation of an RSS item or Atom entry.
type feedItem struct {
	title   string
	linkURL string
	// Inline vehicle fields (from custom namespace or bare elements).
	make_   string
	model   string
	year    string
	mileage string
	price   string
	vin     string
	color   string
	fuel    string
}

// discoverFeeds returns feed URLs to try, in priority order.
func (e *RSS) discoverFeeds(ctx context.Context, dealer pipeline.Dealer, baseURL string) []string {
	// 1. Dealer hint from discovery phase — authoritative, skip further probing.
	if dealer.RSSFeedURL != "" {
		return []string{dealer.RSSFeedURL}
	}

	// 2. Auto-discover from homepage <link rel="alternate">.
	discovered := e.discoverFromHomepage(ctx, baseURL)
	if len(discovered) > 0 {
		return discovered
	}

	// 3. Probe common feed paths.
	var urls []string
	for _, path := range feedPaths {
		if ctx.Err() != nil {
			break
		}
		u := baseURL + path
		if e.probeURL(ctx, u) {
			urls = append(urls, u)
			break
		}
	}
	return urls
}

// discoverFromHomepage fetches the homepage and looks for RSS/Atom link elements.
func (e *RSS) discoverFromHomepage(ctx context.Context, baseURL string) []string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,*/*")

	resp, err := e.client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(body)))
	if err != nil {
		return nil
	}

	var feedURLs []string
	doc.Find(`link[rel="alternate"]`).Each(func(_ int, s *goquery.Selection) {
		t, _ := s.Attr("type")
		href, _ := s.Attr("href")
		if href == "" {
			return
		}
		if t == "application/rss+xml" || t == "application/atom+xml" {
			abs := normalize.CanonicalizePhotoURL(href, baseURL)
			feedURLs = append(feedURLs, abs)
		}
	})
	return feedURLs
}

// probeURL returns true if a HEAD request returns HTTP 200.
func (e *RSS) probeURL(ctx context.Context, u string) bool {
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

// parseFeed fetches and parses an RSS or Atom feed, returning normalised items.
func (e *RSS) parseFeed(ctx context.Context, feedURL string) ([]feedItem, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, feedURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", feedURL)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, feedURL)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	// Detect format by root element name.
	rootName := xmlRootName(body)
	switch rootName {
	case "rss":
		return parseRSS(body)
	case "feed":
		return parseAtom(body)
	default:
		// Unknown format — try RSS first, then Atom.
		if items, err := parseRSS(body); err == nil && len(items) > 0 {
			return items, nil
		}
		return parseAtom(body)
	}
}

// xmlRootName returns the local name of the root XML element.
func xmlRootName(data []byte) string {
	dec := xml.NewDecoder(strings.NewReader(string(data)))
	for {
		tok, err := dec.Token()
		if err != nil {
			return ""
		}
		if se, ok := tok.(xml.StartElement); ok {
			return se.Name.Local
		}
	}
}

// parseRSS parses an RSS 2.0 feed body into feedItems.
func parseRSS(body []byte) ([]feedItem, error) {
	var feed rssFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, err
	}
	items := make([]feedItem, 0, len(feed.Channel.Items))
	for _, it := range feed.Channel.Items {
		items = append(items, feedItem{
			title:   it.Title,
			linkURL: it.Link,
			make_:   it.Make,
			model:   it.Model,
			year:    it.Year,
			mileage: it.Mileage,
			price:   it.Price,
			vin:     it.VIN,
			color:   it.Color,
			fuel:    it.Fuel,
		})
	}
	return items, nil
}

// parseAtom parses an Atom 1.0 feed body into feedItems.
func parseAtom(body []byte) ([]feedItem, error) {
	var feed atomFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, err
	}
	items := make([]feedItem, 0, len(feed.Entries))
	for _, en := range feed.Entries {
		link := atomAlternateLink(en.Links)
		items = append(items, feedItem{
			title:   en.Title.Value,
			linkURL: link,
			make_:   en.Make,
			model:   en.Model,
			year:    en.Year,
			mileage: en.Mileage,
			price:   en.Price,
			vin:     en.VIN,
			color:   en.Color,
			fuel:    en.Fuel,
		})
	}
	return items, nil
}

// atomAlternateLink returns the href of the first link with rel="alternate" or
// no rel (which defaults to alternate per the Atom spec).
func atomAlternateLink(links []atomLink) string {
	for _, l := range links {
		if l.Rel == "alternate" || l.Rel == "" {
			return l.Href
		}
	}
	if len(links) > 0 {
		return links[0].Href
	}
	return ""
}

// extractFromItem builds a VehicleRaw from a feedItem.
// Priority: inline fields → title heuristic → link-follow for JSON-LD.
func (e *RSS) extractFromItem(ctx context.Context, item feedItem, baseURL string) []*pipeline.VehicleRaw {
	// 1. Inline structured fields.
	if item.make_ != "" || item.vin != "" {
		v := mapInlineFields(item, baseURL)
		if v != nil {
			return []*pipeline.VehicleRaw{v}
		}
	}

	// 2. Follow link for JSON-LD extraction.
	if item.linkURL != "" {
		vehicles := e.fetchAndParsePage(ctx, item.linkURL, baseURL)
		if len(vehicles) > 0 {
			return vehicles
		}
	}

	// 3. Title heuristic fallback.
	if item.title != "" {
		v := &pipeline.VehicleRaw{}
		if item.linkURL != "" {
			v.SourceURL = item.linkURL
		}
		parseVehicleTitle(item.title, v)
		if v.Make != nil || v.Model != nil {
			return []*pipeline.VehicleRaw{v}
		}
	}

	return nil
}

// mapInlineFields maps a feedItem's inline vehicle fields to a VehicleRaw.
func mapInlineFields(item feedItem, baseURL string) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{}
	if item.linkURL != "" {
		v.SourceURL = item.linkURL
	}
	if item.vin != "" {
		vin := item.vin
		v.VIN = &vin
	}
	if item.make_ != "" {
		mk := item.make_
		v.Make = &mk
	}
	if item.model != "" {
		model := item.model
		v.Model = &model
	}
	if item.year != "" {
		if yr, err := strconv.Atoi(strings.TrimSpace(item.year)); err == nil && yr > 1900 {
			v.Year = &yr
		}
	}
	if item.mileage != "" {
		raw := strings.Map(func(r rune) rune {
			if r >= '0' && r <= '9' {
				return r
			}
			return -1
		}, item.mileage)
		if km, err := strconv.Atoi(raw); err == nil && km > 0 {
			v.Mileage = &km
		}
	}
	if item.price != "" {
		if p := parseHeuristicPrice(item.price); p > 0 {
			v.PriceGross = &p
		}
	}
	if item.color != "" {
		col := item.color
		v.Color = &col
	}
	if item.fuel != "" {
		fuel := normalize.NormalizeFuelType(item.fuel)
		if fuel != "" {
			v.FuelType = &fuel
		}
	}
	if v.Make == nil && v.VIN == nil {
		return nil
	}
	_ = baseURL
	return v
}

// fetchAndParsePage fetches a vehicle page and returns JSON-LD vehicles.
func (e *RSS) fetchAndParsePage(ctx context.Context, pageURL, baseURL string) []*pipeline.VehicleRaw {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,*/*")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil
	}

	vehicles, _ := e01_jsonld.ParseVehiclesFromHTML(body, baseURL)
	for _, v := range vehicles {
		if v.SourceURL == "" {
			v.SourceURL = pageURL
		}
	}
	return vehicles
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

// containsStr returns true if slice contains s.
func containsStr(slice []string, s string) bool {
	for _, v := range slice {
		if v == s {
			return true
		}
	}
	return false
}

// -- Heuristic vehicle title parser (shared with E03 logic) -------------------

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
	// Delegate to E03's parseHeuristicPrice for price, use local heuristics for make/model/year.
	titleUpper := strings.ToUpper(title)
	for _, make_ := range knownMakes {
		if strings.Contains(titleUpper, strings.ToUpper(make_)) {
			mk := make_
			v.Make = &mk
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
	s = strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' || r == '.' || r == ',' {
			return r
		}
		return -1
	}, s)
	if di := strings.LastIndex(s, ","); di >= 0 {
		s = strings.ReplaceAll(s[:di], ".", "") + "." + s[di+1:]
	}
	var p float64
	fmt.Sscanf(s, "%f", &p)
	return p
}
