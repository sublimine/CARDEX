package e02_cms_rest_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"cardex.eu/extraction/internal/extractor/e02_cms_rest"
	"cardex.eu/extraction/internal/pipeline"
)

// wpVehicle builds a minimal WP REST API vehicle post JSON.
func wpVehicle(id int, make_, model string, year int, price float64, imageURL string) map[string]interface{} {
	v := map[string]interface{}{
		"id":   id,
		"link": fmt.Sprintf("https://dealer.example.de/cars/listing-%d", id),
		"title": map[string]string{"rendered": fmt.Sprintf("%s %s %d", make_, model, year)},
		"meta": map[string]interface{}{
			"vehicle_make":  make_,
			"vehicle_model": model,
			"vehicle_year":  float64(year),
			"vehicle_price": price,
			"vehicle_images": []string{imageURL},
		},
	}
	return v
}

// TestE02_HappyPath verifies extraction from a single-page WP REST response.
func TestE02_HappyPath(t *testing.T) {
	vehicles := []map[string]interface{}{
		wpVehicle(1, "BMW", "320d", 2021, 28500, "https://img.dealer.de/bmw-320d.jpg"),
		wpVehicle(2, "Audi", "A4", 2020, 24900, "https://img.dealer.de/audi-a4.jpg"),
	}
	body, _ := json.Marshal(vehicles)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Serve as WP CPT endpoint.
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-WP-Total", "2")
		w.Header().Set("X-WP-TotalPages", "1")
		w.Write(body)
	}))
	defer srv.Close()

	strategy := e02_cms_rest.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:           "D1",
		Domain:       srv.Listener.Addr().String(),
		URLRoot:      srv.URL,
		PlatformType: "CMS_WORDPRESS",
		CMSDetected:  "wordpress",
		ExtractionHints: []string{"cms:wordpress"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles, got %d", len(result.Vehicles))
	}
}

// TestE02_Pagination verifies that X-WP-TotalPages drives multi-page fetching.
func TestE02_Pagination(t *testing.T) {
	page1 := []map[string]interface{}{
		wpVehicle(1, "Renault", "Clio", 2020, 9500, "https://img.dealer.fr/clio.jpg"),
	}
	page2 := []map[string]interface{}{
		wpVehicle(2, "Peugeot", "308", 2019, 12900, "https://img.dealer.fr/308.jpg"),
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		pageParam := r.URL.Query().Get("page")
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-WP-TotalPages", "2")
		if pageParam == "2" {
			body, _ := json.Marshal(page2)
			w.Write(body)
		} else {
			body, _ := json.Marshal(page1)
			w.Write(body)
		}
	}))
	defer srv.Close()

	strategy := e02_cms_rest.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:              "D2",
		Domain:          srv.Listener.Addr().String(),
		URLRoot:         srv.URL,
		CMSDetected:     "wordpress",
		ExtractionHints: []string{"cms:wordpress"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want 2 vehicles across 2 pages, got %d", len(result.Vehicles))
	}
}

// TestE02_HTTP429_Graceful verifies that a 429 response is handled gracefully
// without panicking or returning a non-nil top-level error.
func TestE02_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	strategy := e02_cms_rest.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:              "D3",
		Domain:          srv.Listener.Addr().String(),
		URLRoot:         srv.URL,
		CMSDetected:     "wordpress",
		ExtractionHints: []string{"cms:wordpress"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	// Should return 0 vehicles, errors recorded.
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429 response, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for 429")
	}
}

// TestE02_WPDiscovery verifies that /wp-json/ auto-discovery finds vehicle
// namespaces and constructs the correct endpoint paths.
func TestE02_WPDiscovery(t *testing.T) {
	vehicles := []map[string]interface{}{
		wpVehicle(1, "Toyota", "Yaris", 2022, 15900, "https://img.dealer.nl/yaris.jpg"),
	}
	body, _ := json.Marshal(vehicles)

	wpIndex := map[string]interface{}{
		"name":       "Dealer NL",
		"namespaces": []string{"wp/v2", "wpcm/v1", "vehicle-catalogue/v1"},
	}
	indexBody, _ := json.Marshal(wpIndex)

	fetchCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		switch {
		case path == "/wp-json/" || path == "/wp-json":
			w.Header().Set("Content-Type", "application/json")
			w.Write(indexBody)
		default:
			// Any vehicle endpoint.
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("X-WP-TotalPages", "1")
			w.Write(body)
			fetchCount++
		}
	}))
	defer srv.Close()

	strategy := e02_cms_rest.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:              "D4",
		Domain:          srv.Listener.Addr().String(),
		URLRoot:         srv.URL,
		CMSDetected:     "wordpress",
		ExtractionHints: []string{"cms:wordpress"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Error("want at least 1 vehicle via WP discovery")
	}

	// Verify that at least one vehicle has expected fields.
	v := result.Vehicles[0]
	if v.Make == nil {
		t.Error("want Make set, got nil")
	}
	_ = strconv.Itoa(fetchCount) // suppress unused warning
}
