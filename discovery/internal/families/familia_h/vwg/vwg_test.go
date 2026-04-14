package vwg_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/vwg"
	"cardex.eu/discovery/internal/kg"
)

// ── mock browser ──────────────────────────────────────────────────────────────

type mockBrowser struct {
	xhrCaptures []*browser.XHRCapture
	xhrErr      error
}

func (m *mockBrowser) FetchHTML(_ context.Context, _ string, _ *browser.FetchOptions) (*browser.FetchResult, error) {
	return &browser.FetchResult{HTML: "<html></html>", StatusCode: 200}, nil
}
func (m *mockBrowser) Screenshot(_ context.Context, _ string, _ *browser.ScreenshotOptions) (*browser.ScreenshotResult, error) {
	return nil, nil
}
func (m *mockBrowser) InterceptXHR(_ context.Context, _ string, _ browser.XHRFilter) ([]*browser.XHRCapture, error) {
	return m.xhrCaptures, m.xhrErr
}
func (m *mockBrowser) Close() error { return nil }

// ── mock KG ───────────────────────────────────────────────────────────────────

type recordingGraph struct {
	kg.KnowledgeGraph
	dealers     []*kg.DealerEntity
	identifiers []*kg.DealerIdentifier
}

func (r *recordingGraph) FindDealerByIdentifier(_ context.Context, _ kg.IdentifierType, _ string) (string, error) {
	return "", nil
}
func (r *recordingGraph) UpsertDealer(_ context.Context, e *kg.DealerEntity) error {
	r.dealers = append(r.dealers, e)
	return nil
}
func (r *recordingGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	r.identifiers = append(r.identifiers, id)
	return nil
}
func (r *recordingGraph) AddLocation(_ context.Context, _ *kg.DealerLocation) error      { return nil }
func (r *recordingGraph) RecordDiscovery(_ context.Context, _ *kg.DiscoveryRecord) error { return nil }

// ── helpers ───────────────────────────────────────────────────────────────────

func mustReadFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile("../../../../testdata/" + name)
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}
	return data
}

// testBrandURLs returns a minimal brand-URL map pointing at a test URL.
func testBrandURLs(locatorURL string) map[string]map[string]string {
	return map[string]map[string]string{
		"VW": {"DE": locatorURL},
	}
}

// ── ParseDealerCapture ────────────────────────────────────────────────────────

// TestParseDealerCapture_DealersEnvelope verifies "dealers" JSON envelope.
func TestParseDealerCapture_DealersEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "vwg_dealer_api.json")
	dealers, err := vwg.ParseDealerCapture(fixture)
	if err != nil {
		t.Fatalf("ParseDealerCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	d0 := dealers[0]
	if d0.ID != "DE-VW-00123" {
		t.Errorf("dealers[0].ID = %q, want DE-VW-00123", d0.ID)
	}
	if d0.Name != "VW Autohaus Berlin GmbH" {
		t.Errorf("dealers[0].Name = %q", d0.Name)
	}
	if d0.Address.PostalCode != "10115" {
		t.Errorf("dealers[0].PostalCode = %q", d0.Address.PostalCode)
	}
	if d0.Address.CountryCode != "DE" {
		t.Errorf("dealers[0].CountryCode = %q", d0.Address.CountryCode)
	}

	// Second dealer uses alternate field names (dealerId, zipCode, country).
	d1 := dealers[1]
	if d1.DealerID != "DE-VW-00456" {
		t.Errorf("dealers[1].DealerID = %q, want DE-VW-00456", d1.DealerID)
	}
	if d1.Address.ZipCode != "10117" {
		t.Errorf("dealers[1].ZipCode = %q", d1.Address.ZipCode)
	}
}

// TestParseDealerCapture_AlternativeEnvelopes verifies results/data/items/array envelopes.
func TestParseDealerCapture_AlternativeEnvelopes(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{"results", `{"results":[{"id":"R1","name":"Result Dealer","address":{"countryCode":"DE"}}]}`},
		{"data", `{"data":[{"id":"D1","name":"Data Dealer","address":{"countryCode":"FR"}}]}`},
		{"items", `{"items":[{"id":"I1","name":"Item Dealer","address":{"countryCode":"NL"}}]}`},
		{"array", `[{"id":"A1","name":"Array Dealer","address":{"countryCode":"CH"}}]`},
	}
	for _, tc := range cases {
		dealers, err := vwg.ParseDealerCapture([]byte(tc.body))
		if err != nil {
			t.Errorf("%s: unexpected error: %v", tc.name, err)
			continue
		}
		if len(dealers) != 1 {
			t.Errorf("%s: want 1 dealer, got %d", tc.name, len(dealers))
		}
	}
}

// TestParseDealerCapture_Empty returns nil for empty body.
func TestParseDealerCapture_Empty(t *testing.T) {
	dealers, err := vwg.ParseDealerCapture(nil)
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if len(dealers) != 0 {
		t.Errorf("expected empty, got %v", dealers)
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := vwg.New(nil, nil)
	if loc.OEMID() != "VWG" {
		t.Errorf("OEMID = %q, want VWG", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCaptureUpserts verifies that XHR captures are parsed and upserted.
func TestRun_XHRCaptureUpserts(t *testing.T) {
	fixture := mustReadFixture(t, "vwg_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://www.vw-test.example/api/dealers?zip=10115",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := vwg.NewWithURLs(graph, mb, testBrandURLs("https://www.vw-test.example/haendler"))

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if len(graph.dealers) != 2 {
		t.Errorf("upserted dealers = %d, want 2", len(graph.dealers))
	}

	names := map[string]bool{}
	for _, d := range graph.dealers {
		names[d.CanonicalName] = true
	}
	if !names["VW Autohaus Berlin GmbH"] {
		t.Error("expected 'VW Autohaus Berlin GmbH' in upserted dealers")
	}

	// OEM_DEALER_ID identifiers should have "VW:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if len(id.IdentifierValue) < 3 || id.IdentifierValue[:3] != "VW:" {
				t.Errorf("OEM_DEALER_ID %q missing VW: prefix", id.IdentifierValue)
			}
		}
	}
}

// TestRun_NilBrowser returns empty result when browser is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := vwg.New(graph, nil)
	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}

// TestRun_NoXHRCaptures logs deferred but returns no error.
func TestRun_NoXHRCaptures(t *testing.T) {
	mb := &mockBrowser{xhrCaptures: nil}
	graph := &recordingGraph{}
	loc := vwg.NewWithURLs(graph, mb, testBrandURLs("https://www.vw-test.example/haendler"))

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR, got %d", result.Discovered)
	}
}

// TestRun_Deduplication verifies same dealer from multiple postcode sweeps
// is counted once.
func TestRun_Deduplication(t *testing.T) {
	// Single dealer returned for every postcode sweep.
	singleDealerBody := []byte(`{"dealers":[{
		"id":"DE-VW-99999",
		"name":"Same Dealer Everywhere",
		"address":{"street":"Test Str 1","postalCode":"10115","city":"Berlin","countryCode":"DE"}
	}]}`)

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{RequestURL: "http://x/api", ResponseStatus: 200, ResponseBody: singleDealerBody},
		},
	}
	graph := &recordingGraph{}
	loc := vwg.NewWithURLs(graph, mb, testBrandURLs("https://www.vw-test.example/haendler"))

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// 10 postcodes swept, same dealer returned each time → 1 discovered.
	if result.Discovered != 1 {
		t.Errorf("expected 1 discovered (deduplication), got %d", result.Discovered)
	}
}

// TestRun_UnconfiguredCountry returns empty for country with no postcodes.
func TestRun_UnconfiguredCountry(t *testing.T) {
	mb := &mockBrowser{}
	graph := &recordingGraph{}
	loc := vwg.NewWithURLs(graph, mb, testBrandURLs("https://example.com"))

	result, err := loc.Run(context.Background(), "PT") // Portugal — not configured
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0, got %d", result.Discovered)
	}
}
