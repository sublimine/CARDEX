package e04_rss_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/extraction/internal/extractor/e04_rss"
	"cardex.eu/extraction/internal/pipeline"
)

// vehicleHTML returns a minimal HTML page embedding a JSON-LD Car block so
// that e01_jsonld.ParseVehiclesFromHTML can extract structured data.
func vehicleHTML(vin, make_, model string, year int, price float64) string {
	return fmt.Sprintf(`<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Car",
"vehicleIdentificationNumber":"%s",
"brand":{"@type":"Brand","name":"%s"},
"model":"%s",
"vehicleModelDate":"%d",
"offers":{"@type":"Offer","price":"%.0f","priceCurrency":"EUR"}}
</script></head><body><h1>%s %s</h1></body></html>`,
		vin, make_, model, year, price, make_, model)
}

// rss2Feed builds a minimal RSS 2.0 feed XML body.
// Each vehicle in the items slice is encoded with inline <make>, <model>,
// <year>, <price>, and <vin> elements.
func rss2Feed(baseURL string, items []map[string]string) string {
	body := `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Dealer Feed</title>`
	for _, it := range items {
		body += "<item>"
		body += fmt.Sprintf("<title>%s %s %s</title>", it["make"], it["model"], it["year"])
		body += fmt.Sprintf("<link>%s%s</link>", baseURL, it["path"])
		body += fmt.Sprintf("<make>%s</make>", it["make"])
		body += fmt.Sprintf("<model>%s</model>", it["model"])
		body += fmt.Sprintf("<year>%s</year>", it["year"])
		body += fmt.Sprintf("<price>%s</price>", it["price"])
		body += fmt.Sprintf("<vin>%s</vin>", it["vin"])
		body += "</item>"
	}
	body += "</channel></rss>"
	return body
}

// atomFeed builds a minimal Atom 1.0 feed with entries that have only a title
// and an alternate link — no inline vehicle data.  E04 must follow the links.
func atomFeedXML(entries []map[string]string) string {
	body := `<?xml version="1.0" encoding="UTF-8"?>`
	body += `<feed xmlns="http://www.w3.org/2005/Atom">`
	body += `<title>Dealer Atom Feed</title>`
	for _, e := range entries {
		body += "<entry>"
		body += fmt.Sprintf("<title>%s</title>", e["title"])
		body += fmt.Sprintf(`<link rel="alternate" href="%s"/>`, e["href"])
		body += fmt.Sprintf("<id>%s</id>", e["href"])
		body += "</entry>"
	}
	body += "</feed>"
	return body
}

// TestE04_RSS2_VehicleItems verifies that inline vehicle fields in an RSS 2.0
// feed (<make>, <model>, <year>, <price>, <vin>) are extracted without needing
// to follow item links.
func TestE04_RSS2_VehicleItems(t *testing.T) {
	// Track whether vehicle page links are ever fetched.
	vehiclePagesFetched := 0

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/feed.rss":
			w.Header().Set("Content-Type", "application/rss+xml")
			items := []map[string]string{
				{"make": "BMW", "model": "320d", "year": "2021", "price": "28500", "vin": "VIN001", "path": "/vehicles/1"},
				{"make": "Audi", "model": "A4", "year": "2020", "price": "24900", "vin": "VIN002", "path": "/vehicles/2"},
			}
			fmt.Fprint(w, rss2Feed("http://"+r.Host, items))
		default:
			// Vehicle pages — track if fetched, but inline data should be enough.
			vehiclePagesFetched++
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN_PAGE", "Ford", "Focus", 2019, 10000))
		}
	}))
	defer srv.Close()

	strategy := e04_rss.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:          "D1",
		Domain:      srv.Listener.Addr().String(),
		URLRoot:     srv.URL,
		RSSFeedURL:  srv.URL + "/feed.rss", // hint to skip homepage/probe discovery
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from inline RSS fields, got %d", len(result.Vehicles))
	}
	// Inline fields should have been used — verify make/model on first vehicle.
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set from inline RSS field, got nil/empty")
	}
	if v.VIN == nil || *v.VIN == "" {
		t.Error("want VIN set from inline RSS field, got nil/empty")
	}
	// Inline extraction means vehicle pages should not have been fetched.
	if vehiclePagesFetched > 0 {
		t.Errorf("vehicle pages should not be fetched when inline fields are present, got %d fetches", vehiclePagesFetched)
	}
}

// TestE04_Atom_FollowLinks verifies that Atom 1.0 entries with only a link
// (no inline vehicle data) cause E04 to follow the entry link and extract
// vehicle data via JSON-LD from the linked page.
func TestE04_Atom_FollowLinks(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/atom.xml":
			w.Header().Set("Content-Type", "application/atom+xml")
			entries := []map[string]string{
				{"title": "Renault Clio 2020", "href": host + "/cars/renault-clio-1"},
				{"title": "Peugeot 308 2019", "href": host + "/cars/peugeot-308-2"},
			}
			fmt.Fprint(w, atomFeedXML(entries))
		case "/cars/renault-clio-1":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN003", "Renault", "Clio", 2020, 9500))
		case "/cars/peugeot-308-2":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN004", "Peugeot", "308", 2019, 12900))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e04_rss.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:         "D2",
		Domain:     srv.Listener.Addr().String(),
		URLRoot:    srv.URL,
		RSSFeedURL: srv.URL + "/atom.xml",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles via Atom link-follow, got %d", len(result.Vehicles))
	}
	if result.Strategy != "E04" {
		t.Errorf("want strategy E04, got %q", result.Strategy)
	}
}

// TestE04_AutoDiscovery verifies that E04 discovers the feed URL from a
// homepage <link rel="alternate" type="application/rss+xml"> element when no
// RSSFeedURL hint is present.
func TestE04_AutoDiscovery(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/":
			// Homepage with <link rel="alternate"> pointing at the RSS feed.
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprintf(w, `<!DOCTYPE html><html><head>
<link rel="alternate" type="application/rss+xml" href="%s/feed.rss" title="Vehicles"/>
</head><body><h1>Dealer</h1></body></html>`, host)
		case "/feed.rss":
			w.Header().Set("Content-Type", "application/rss+xml")
			items := []map[string]string{
				{"make": "Toyota", "model": "Yaris", "year": "2022", "price": "15900", "vin": "VIN005", "path": "/vehicles/1"},
			}
			fmt.Fprint(w, rss2Feed(host, items))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	// No RSSFeedURL hint — auto-discovery must find the feed.
	strategy := e04_rss.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Error("want >=1 vehicle from auto-discovered feed, got 0")
	}
	if result.SourceURL == "" {
		t.Error("want SourceURL set to discovered feed URL, got empty")
	}
}

// TestE04_HTTP429_Graceful verifies that a 429 response on the feed URL is
// handled gracefully: 0 vehicles, error recorded, no panic.
func TestE04_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Feed URL returns 429.
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	strategy := e04_rss.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:         "D4",
		Domain:     srv.Listener.Addr().String(),
		URLRoot:    srv.URL,
		RSSFeedURL: srv.URL + "/feed.rss",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429 response, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for 429 feed response")
	}
}
