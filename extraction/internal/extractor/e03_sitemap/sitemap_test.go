package e03_sitemap_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/extraction/internal/extractor/e03_sitemap"
	"cardex.eu/extraction/internal/pipeline"
)

// vehicleHTML returns a minimal HTML page with a JSON-LD Car block.
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

// urlsetXML returns a sitemap urlset XML with the given URLs.
func urlsetXML(baseURL string, paths ...string) string {
	var sb strings.Builder
	sb.WriteString(`<?xml version="1.0" encoding="UTF-8"?>`)
	sb.WriteString(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`)
	for _, p := range paths {
		sb.WriteString(fmt.Sprintf("<url><loc>%s%s</loc></url>", baseURL, p))
	}
	sb.WriteString(`</urlset>`)
	return sb.String()
}

// sitemapIndexXML returns a sitemapindex XML pointing to the given sub-sitemap URLs.
func sitemapIndexXML(subURLs ...string) string {
	var sb strings.Builder
	sb.WriteString(`<?xml version="1.0" encoding="UTF-8"?>`)
	sb.WriteString(`<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`)
	for _, u := range subURLs {
		sb.WriteString(fmt.Sprintf("<sitemap><loc>%s</loc></sitemap>", u))
	}
	sb.WriteString(`</sitemapindex>`)
	return sb.String()
}

// TestE03_SimpleSitemap_HappyPath verifies that a flat urlset sitemap with two
// vehicle URLs results in two vehicles being extracted via JSON-LD.
func TestE03_SimpleSitemap_HappyPath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/robots.txt":
			// robots.txt advertises the sitemap.
			fmt.Fprintf(w, "User-agent: *\nSitemap: %s/sitemap.xml\n", "http://"+r.Host)
		case "/sitemap.xml":
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, urlsetXML("http://"+r.Host, "/vehicles/bmw-320d-1", "/vehicles/audi-a4-2"))
		case "/vehicles/bmw-320d-1":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN001", "BMW", "320d", 2021, 28500))
		case "/vehicles/audi-a4-2":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN002", "Audi", "A4", 2020, 24900))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e03_sitemap.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D1",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles, got %d", len(result.Vehicles))
	}
	if result.Strategy != "E03" {
		t.Errorf("want strategy E03, got %q", result.Strategy)
	}
}

// TestE03_SitemapIndex_SubSitemaps verifies that a sitemapindex pointing to two
// vehicle sub-sitemaps resolves both and extracts vehicles from each.
func TestE03_SitemapIndex_SubSitemaps(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/robots.txt":
			fmt.Fprintf(w, "User-agent: *\nSitemap: %s/sitemap_index.xml\n", host)
		case "/sitemap_index.xml":
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, sitemapIndexXML(
				host+"/sitemap-vehicles.xml",
				host+"/sitemap-cars.xml",
			))
		case "/sitemap-vehicles.xml":
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, urlsetXML(host, "/vehicles/renault-clio-3"))
		case "/sitemap-cars.xml":
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, urlsetXML(host, "/cars/peugeot-308-4"))
		case "/vehicles/renault-clio-3":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN003", "Renault", "Clio", 2020, 9500))
		case "/cars/peugeot-308-4":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN004", "Peugeot", "308", 2019, 12900))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e03_sitemap.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from 2 sub-sitemaps, got %d", len(result.Vehicles))
	}
}

// TestE03_NonVehicleURLs_Filtered verifies that URLs not matching vehicle path
// patterns are filtered out and their pages are never fetched.
func TestE03_NonVehicleURLs_Filtered(t *testing.T) {
	fetchedPaths := map[string]int{}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fetchedPaths[r.URL.Path]++
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/robots.txt":
			fmt.Fprintf(w, "User-agent: *\nSitemap: %s/sitemap.xml\n", host)
		case "/sitemap.xml":
			// Mix of vehicle and non-vehicle paths.
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, urlsetXML(host,
				"/about-us",
				"/contact",
				"/blog/news-2024",
				"/vehicles/toyota-yaris-5",
			))
		case "/vehicles/toyota-yaris-5":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, vehicleHTML("VIN005", "Toyota", "Yaris", 2022, 15900))
		default:
			// Non-vehicle pages — should never be fetched.
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e03_sitemap.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Exactly 1 vehicle from the 1 vehicle-path URL.
	if len(result.Vehicles) != 1 {
		t.Errorf("want 1 vehicle (filtered), got %d", len(result.Vehicles))
	}
	// Non-vehicle pages must NOT have been fetched.
	for _, nonVehicle := range []string{"/about-us", "/contact", "/blog/news-2024"} {
		if fetchedPaths[nonVehicle] > 0 {
			t.Errorf("non-vehicle path %q was fetched but should have been filtered", nonVehicle)
		}
	}
}

// TestE03_HTTP429_Graceful verifies that a 429 response on vehicle page fetches
// is handled gracefully: 0 vehicles returned, errors recorded, no panic.
func TestE03_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/robots.txt":
			fmt.Fprintf(w, "User-agent: *\nSitemap: %s/sitemap.xml\n", host)
		case "/sitemap.xml":
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, urlsetXML(host, "/vehicles/car-1", "/vehicles/car-2"))
		default:
			// All vehicle page requests get rate-limited.
			w.WriteHeader(http.StatusTooManyRequests)
		}
	}))
	defer srv.Close()

	strategy := e03_sitemap.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D4",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429 response, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for 429 vehicle page responses")
	}
}
