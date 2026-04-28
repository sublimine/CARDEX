package e05_dms_api_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/extraction/internal/extractor/e05_dms_api"
	"cardex.eu/extraction/internal/pipeline"
)

// TestE05_CDK_HappyPath verifies extraction from a CDK Global inventory endpoint.
// The response uses CDK's typical JSON schema with an "inventory" array.
func TestE05_CDK_HappyPath(t *testing.T) {
	inventory := map[string]interface{}{
		"inventory": []map[string]interface{}{
			{
				"vin":     "WBAWBAWBA12345001",
				"make":    "BMW",
				"model":   "320d",
				"year":    2021,
				"price":   28500.0,
				"mileage": 45000,
				"color":   "Blue",
			},
			{
				"vin":     "WAUAAAAWAU12345002",
				"make":    "Audi",
				"model":   "A4",
				"year":    2020,
				"price":   24900.0,
				"mileage": 55000,
			},
		},
	}
	body, _ := json.Marshal(inventory)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/cdk-portal/api/inventory" {
			w.Header().Set("Content-Type", "application/json")
			w.Write(body)
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	strategy := e05_dms_api.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:          "D1",
		Domain:      srv.Listener.Addr().String(),
		URLRoot:     srv.URL,
		DMSProvider: "CDK Global",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles, got %d", len(result.Vehicles))
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set, got nil/empty")
	}
	if v.PriceGross == nil || *v.PriceGross == 0 {
		t.Error("want PriceGross set, got nil/zero")
	}
	if result.Strategy != "E05" {
		t.Errorf("want strategy E05, got %q", result.Strategy)
	}
}

// TestE05_incadea_NestedPrice verifies that incadea's nested price object
// {"price": {"value": 18500, "currency": "EUR"}} is correctly unwrapped.
func TestE05_incadea_NestedPrice(t *testing.T) {
	items := map[string]interface{}{
		"items": []map[string]interface{}{
			{
				"vin":          "VSSZZZAAZZE123456",
				"manufacturer": "Skoda",
				"modelName":    "Octavia",
				"modelYear":    2019,
				"price": map[string]interface{}{
					"value":    18500.0,
					"currency": "EUR",
				},
			},
			{
				"vin":          "VSSZZZAAZZE654321",
				"manufacturer": "Volkswagen",
				"modelName":    "Golf",
				"modelYear":    2020,
				"price": map[string]interface{}{
					"value":    22900.0,
					"currency": "EUR",
				},
			},
		},
	}
	body, _ := json.Marshal(items)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/incadea-cms/inventory" {
			w.Header().Set("Content-Type", "application/json")
			w.Write(body)
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	strategy := e05_dms_api.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:          "D2",
		Domain:      srv.Listener.Addr().String(),
		URLRoot:     srv.URL,
		DMSProvider: "incadea",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles, got %d", len(result.Vehicles))
	}
	// Verify nested price was correctly extracted.
	v := result.Vehicles[0]
	if v.PriceGross == nil || *v.PriceGross <= 0 {
		t.Error("want PriceGross set from nested incadea price object, got nil/zero")
	}
}

// TestE05_AutoLine_XML verifies that AutoLine's XML feed format is correctly
// parsed and mapped to VehicleRaw records.
func TestE05_AutoLine_XML(t *testing.T) {
	xmlBody := `<?xml version="1.0" encoding="UTF-8"?>
<vehicles>
  <vehicle>
    <vin>VF1AAZZZAAZ000001</vin>
    <make>Renault</make>
    <model>Clio</model>
    <year>2020</year>
    <mileage>35000</mileage>
    <price>9500.00</price>
    <color>Red</color>
    <fuel>gasoline</fuel>
    <currency>EUR</currency>
  </vehicle>
  <vehicle>
    <vin>VF3AAZZZAAZ000002</vin>
    <make>Peugeot</make>
    <model>308</model>
    <year>2019</year>
    <mileage>48000</mileage>
    <price>12900.00</price>
    <currency>EUR</currency>
  </vehicle>
</vehicles>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/autoline-feed.xml" {
			w.Header().Set("Content-Type", "application/xml")
			fmt.Fprint(w, xmlBody)
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	strategy := e05_dms_api.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:          "D3",
		Domain:      srv.Listener.Addr().String(),
		URLRoot:     srv.URL,
		DMSProvider: "autoline",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from AutoLine XML, got %d", len(result.Vehicles))
	}
	v := result.Vehicles[0]
	if v.Make == nil {
		t.Error("want Make set from XML, got nil")
	}
	if v.Mileage == nil || *v.Mileage == 0 {
		t.Error("want Mileage set from XML, got nil/zero")
	}
}

// TestE05_HTTP429_Graceful verifies that a 429 response on the DMS endpoint
// is handled gracefully: 0 vehicles, error recorded, no panic.
func TestE05_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	strategy := e05_dms_api.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:          "D4",
		Domain:      srv.Listener.Addr().String(),
		URLRoot:     srv.URL,
		DMSProvider: "modix",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429 response, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for 429 DMS endpoint response")
	}
}
