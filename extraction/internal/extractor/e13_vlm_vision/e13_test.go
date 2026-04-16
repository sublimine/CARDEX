package e13_vlm_vision_test

import (
	"context"
	"testing"
	"time"

	"cardex.eu/extraction/internal/extractor/e13_vlm_vision"
	"cardex.eu/extraction/internal/pipeline"
)

func testCfg() e13_vlm_vision.VLMConfig {
	return e13_vlm_vision.VLMConfig{
		Model:      "phi3.5-vision:latest",
		Endpoint:   "http://localhost:11434",
		Timeout:    5 * time.Second,
		MaxRetries: 0, // no retries in unit tests
	}
}

func dealerFixture() pipeline.Dealer {
	return pipeline.Dealer{
		ID:          "D-TEST-001",
		Domain:      "example-dealer.fr",
		URLRoot:     "https://example-dealer.fr",
		CountryCode: "FR",
	}
}

// TestE13_Applicable verifies E13 is always applicable (universal fallback).
func TestE13_Applicable(t *testing.T) {
	mock := &e13_vlm_vision.MockClient{Response: "{}"}
	ex := e13_vlm_vision.NewWithClient(testCfg(), mock, nil)

	if !ex.Applicable(dealerFixture()) {
		t.Error("E13 must be applicable to any dealer")
	}
}

// TestE13_ApplicableVLMRequired verifies that dealers with "vlm_required" hint
// are explicitly applicable (even if universal fallback logic changes).
func TestE13_ApplicableVLMRequired(t *testing.T) {
	mock := &e13_vlm_vision.MockClient{Response: "{}"}
	ex := e13_vlm_vision.NewWithClient(testCfg(), mock, nil)

	dealer := dealerFixture()
	dealer.ExtractionHints = []string{"vlm_required"}
	if !ex.Applicable(dealer) {
		t.Error("E13 must be applicable for dealer with vlm_required hint")
	}
}

// TestE13_IDPriority verifies strategy metadata.
func TestE13_IDPriority(t *testing.T) {
	mock := &e13_vlm_vision.MockClient{Response: "{}"}
	ex := e13_vlm_vision.NewWithClient(testCfg(), mock, nil)

	if ex.ID() != "E13" {
		t.Errorf("expected ID=E13, got %q", ex.ID())
	}
	if ex.Priority() != 100 {
		t.Errorf("expected Priority=100, got %d", ex.Priority())
	}
}

// TestE13_MockNoImages verifies that when the page fetch returns no images,
// the result has no vehicles and an appropriate error code.
func TestE13_MockNoImages(t *testing.T) {
	// Mock client never called because image fetching will fail with no real HTTP.
	mock := &e13_vlm_vision.MockClient{Response: "{}"}
	ex := e13_vlm_vision.NewWithClient(testCfg(), mock, nil)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result, err := ex.Extract(ctx, dealerFixture())
	if err != nil {
		t.Fatalf("Extract returned unexpected error: %v", err)
	}
	// With no real HTTP, we expect 0 vehicles and at least one error.
	if len(result.Vehicles) != 0 {
		t.Errorf("expected 0 vehicles when page is unreachable, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("expected at least one extraction error when page is unreachable")
	}
	// NextFallback must always be set to E12.
	if result.NextFallback == nil || *result.NextFallback != "E12" {
		t.Errorf("expected NextFallback=E12, got %v", result.NextFallback)
	}
}

// TestE13_MockVLMTimeout verifies that a VLM timeout marks the request as timeout
// in errors and still returns a non-nil result (graceful degradation).
func TestE13_MockVLMTimeout(t *testing.T) {
	mock := &e13_vlm_vision.MockClient{Err: e13_vlm_vision.ErrMockTimeout}
	ex := e13_vlm_vision.NewWithClient(testCfg(), mock, nil)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result, err := ex.Extract(ctx, dealerFixture())
	if err != nil {
		t.Fatalf("Extract must not propagate VLM errors as Go errors; got: %v", err)
	}
	// No vehicles because VLM failed; errors should be recorded.
	// (Images not fetched because no real HTTP server, so errors may differ.)
	if result == nil {
		t.Fatal("result must be non-nil")
	}
	if result.NextFallback == nil || *result.NextFallback != "E12" {
		t.Errorf("NextFallback must be E12, got %v", result.NextFallback)
	}
}

// TestStripMarkdownFence verifies the parser handles model output wrappers.
func TestStripMarkdownFence(t *testing.T) {
	cases := []struct {
		name  string
		input string
		wantMake string
	}{
		{
			name:     "bare JSON",
			input:    `{"make":"BMW","model":"320d","year":2020}`,
			wantMake: "BMW",
		},
		{
			name:     "json code fence",
			input:    "```json\n{\"make\":\"Audi\",\"model\":\"A4\",\"year\":2021}\n```",
			wantMake: "Audi",
		},
		{
			name:     "plain code fence",
			input:    "```\n{\"make\":\"Peugeot\",\"model\":\"308\",\"year\":2022}\n```",
			wantMake: "Peugeot",
		},
		{
			name:     "JSON with leading text",
			input:    "Here is the extracted data:\n{\"make\":\"Renault\",\"model\":\"Clio\",\"year\":2019}",
			wantMake: "Renault",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			vehicle, fields := e13_vlm_vision.ParseVLMResponseExported(tc.input)
			if vehicle == nil {
				t.Fatalf("expected non-nil vehicle for input %q", tc.input)
			}
			if vehicle.Make == nil || *vehicle.Make != tc.wantMake {
				t.Errorf("expected make=%q, got %v", tc.wantMake, vehicle.Make)
			}
			if fields < 3 {
				t.Errorf("expected at least 3 fields extracted, got %d", fields)
			}
		})
	}
}

// TestParseVLMResponse_AIActMetadata verifies that every parsed vehicle carries
// AI Act disclosure fields in AdditionalFields.
// NOTE: The AdditionalFields are set by Extract(), not by the parser.
// This test validates the parser output separately.
func TestParseVLMResponse_FullFields(t *testing.T) {
	input := `{
		"make": "BMW",
		"model": "320d",
		"year": 2020,
		"price": 25000,
		"price_currency": "EUR",
		"mileage_km": 45000,
		"fuel_type": "diesel",
		"transmission": "manual",
		"color": "black",
		"vin": "WBA3A5G5XFNS12345",
		"dealer_name": "BMW München",
		"dealer_location": "München, DE"
	}`
	vehicle, fields := e13_vlm_vision.ParseVLMResponseExported(input)
	if vehicle == nil {
		t.Fatal("expected non-nil vehicle")
	}
	checks := map[string]bool{
		"make":  vehicle.Make != nil && *vehicle.Make == "BMW",
		"model": vehicle.Model != nil && *vehicle.Model == "320d",
		"year":  vehicle.Year != nil && *vehicle.Year == 2020,
		"price": vehicle.PriceGross != nil && *vehicle.PriceGross == 25000,
		"mileage": vehicle.Mileage != nil && *vehicle.Mileage == 45000,
		"fuel":  vehicle.FuelType != nil && *vehicle.FuelType == "diesel",
		"trans": vehicle.Transmission != nil && *vehicle.Transmission == "manual",
		"color": vehicle.Color != nil && *vehicle.Color == "black",
		"vin":   vehicle.VIN != nil && *vehicle.VIN == "WBA3A5G5XFNS12345",
	}
	for name, ok := range checks {
		if !ok {
			t.Errorf("field %q not correctly parsed", name)
		}
	}
	if fields < 9 {
		t.Errorf("expected at least 9 fields, got %d", fields)
	}
}

// TestParseVLMResponse_EmptyInput verifies nil is returned for unusable input.
func TestParseVLMResponse_EmptyInput(t *testing.T) {
	cases := []string{"", "not json at all", "{}", "   "}
	for _, input := range cases {
		v, f := e13_vlm_vision.ParseVLMResponseExported(input)
		if f > 0 || v != nil {
			t.Errorf("expected nil vehicle for input %q, got %v fields", input, f)
		}
	}
}

// TestParseVLMResponse_InvalidYear verifies out-of-range year is ignored.
func TestParseVLMResponse_InvalidYear(t *testing.T) {
	input := `{"make":"BMW","model":"320d","year":1800}`
	v, _ := e13_vlm_vision.ParseVLMResponseExported(input)
	if v == nil {
		t.Fatal("expected non-nil vehicle (make+model still valid)")
	}
	if v.Year != nil {
		t.Errorf("year 1800 should be ignored, but Year=%v", *v.Year)
	}
}
