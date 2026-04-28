package e07_playwright_xhr_test

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"cardex.eu/extraction/internal/extractor/e07_playwright_xhr"
	"cardex.eu/extraction/internal/pipeline"
)

// mockInterceptor implements XHRInterceptor for testing.
// It returns pre-configured captures when InterceptXHR is called.
type mockInterceptor struct {
	captures []*e07_playwright_xhr.XHRCapture
	err      error
}

func (m *mockInterceptor) InterceptXHR(_ context.Context, _ string, _ func(string) bool) ([]*e07_playwright_xhr.XHRCapture, error) {
	return m.captures, m.err
}

// makeCapture builds an XHRCapture with a JSON body marshalled from v.
func makeCapture(apiURL string, body interface{}) *e07_playwright_xhr.XHRCapture {
	b, _ := json.Marshal(body)
	return &e07_playwright_xhr.XHRCapture{
		RequestURL:     apiURL,
		ResponseBody:   b,
		ResponseStatus: http.StatusOK,
	}
}

// TestE07_XHR_RootArray verifies that when an XHR response contains a JSON
// root array of vehicle objects, all vehicles are extracted.
func TestE07_XHR_RootArray(t *testing.T) {
	vehicles := []map[string]interface{}{
		{"vin": "WBAWBAWBA12345001", "make": "BMW", "model": "320d", "year": 2021, "price": 28500.0, "mileage": 45000},
		{"vin": "WAUAAAAWAU12345002", "make": "Audi", "model": "A4", "year": 2020, "price": 24900.0},
	}
	interceptor := &mockInterceptor{
		captures: []*e07_playwright_xhr.XHRCapture{
			makeCapture("http://dealer.example.de/api/vehicles", vehicles),
		},
	}

	strategy := e07_playwright_xhr.NewWithInterceptor(interceptor, 0)
	dealer := pipeline.Dealer{
		ID:      "D1",
		Domain:  "dealer.example.de",
		URLRoot: "http://dealer.example.de",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from XHR root array, got %d", len(result.Vehicles))
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set, got nil/empty")
	}
	if result.Strategy != "E07" {
		t.Errorf("want strategy E07, got %q", result.Strategy)
	}
}

// TestE07_XHR_ObjectWrapper verifies that vehicles wrapped in a common JSON
// key (e.g. "results", "inventory") are correctly extracted.
func TestE07_XHR_ObjectWrapper(t *testing.T) {
	payload := map[string]interface{}{
		"total": 3,
		"results": []map[string]interface{}{
			{"vin": "VF1AAZZZAAZ000001", "make": "Renault", "model": "Clio", "year": 2020, "price": 9500.0},
			{"vin": "VF3AAZZZAAZ000002", "make": "Peugeot", "model": "308", "year": 2019, "price": 12900.0},
			{"vin": "VF7AAZZZAAZ000003", "make": "Citroen", "model": "C3", "year": 2021, "price": 11500.0},
		},
	}
	interceptor := &mockInterceptor{
		captures: []*e07_playwright_xhr.XHRCapture{
			makeCapture("http://dealer.fr/api/inventory?page=1", payload),
		},
	}

	strategy := e07_playwright_xhr.NewWithInterceptor(interceptor, 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		Domain:  "dealer.fr",
		URLRoot: "http://dealer.fr",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 3 {
		t.Errorf("want >=3 vehicles from wrapped JSON, got %d", len(result.Vehicles))
	}
}

// TestE07_EmptyCaptures verifies that when the interceptor returns no matching
// XHR responses, E07 returns 0 vehicles without errors.
func TestE07_EmptyCaptures(t *testing.T) {
	interceptor := &mockInterceptor{captures: nil}

	strategy := e07_playwright_xhr.NewWithInterceptor(interceptor, 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  "dealer.example.com",
		URLRoot: "http://dealer.example.com",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from empty captures, got %d", len(result.Vehicles))
	}
	if len(result.Errors) > 0 {
		t.Errorf("want 0 errors for empty captures, got %d: %v", len(result.Errors), result.Errors)
	}
}

// TestE07_MalformedJSON_Graceful verifies that malformed JSON in an XHR
// response body does not cause a panic or top-level error — it is silently
// skipped and 0 vehicles are returned.
func TestE07_MalformedJSON_Graceful(t *testing.T) {
	interceptor := &mockInterceptor{
		captures: []*e07_playwright_xhr.XHRCapture{
			{
				RequestURL:     "http://dealer.example.com/api/vehicles",
				ResponseBody:   []byte(`{not valid json!!!`),
				ResponseStatus: http.StatusOK,
			},
			{
				RequestURL:     "http://dealer.example.com/api/other",
				ResponseBody:   []byte(`<html>not json at all</html>`),
				ResponseStatus: http.StatusOK,
			},
		},
	}

	strategy := e07_playwright_xhr.NewWithInterceptor(interceptor, 0)
	dealer := pipeline.Dealer{
		ID:      "D4",
		Domain:  "dealer.example.com",
		URLRoot: "http://dealer.example.com",
	}

	// Must not panic.
	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from malformed JSON, got %d", len(result.Vehicles))
	}
}
