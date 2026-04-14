package stellantis_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/stellantis"
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
func (r *recordingGraph) UpsertWebPresence(_ context.Context, _ *kg.DealerWebPresence) error {
	return nil
}
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
// Only PEUGEOT/FR is populated so tests run a single brand sweep.
func testBrandURLs(locatorURL string) map[string]map[string]string {
	return map[string]map[string]string{
		"PEUGEOT": {"FR": locatorURL},
	}
}

// ── ParseCapture ──────────────────────────────────────────────────────────────

// TestParseCapture_DealersEnvelope verifies "dealers" JSON envelope parsing
// using the stellantis_dealer_api.json fixture.
func TestParseCapture_DealersEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "stellantis_dealer_api.json")
	dealers, err := stellantis.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer uses "id" field.
	d0 := dealers[0]
	if d0.CanonicalID() != "FR-PEU-001" {
		t.Errorf("dealers[0].CanonicalID() = %q, want FR-PEU-001", d0.CanonicalID())
	}
	if d0.CanonicalName() != "Peugeot Paris Île-de-France" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}

	// Second dealer uses "dealerId" field.
	d1 := dealers[1]
	if d1.CanonicalID() != "FR-PEU-002" {
		t.Errorf("dealers[1].CanonicalID() = %q, want FR-PEU-002", d1.CanonicalID())
	}
	if d1.CanonicalName() != "Citroën Lyon Centre" {
		t.Errorf("dealers[1].CanonicalName() = %q", d1.CanonicalName())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := stellantis.New(nil, nil)
	if loc.OEMID() != "STELLANTIS" {
		t.Errorf("OEMID = %q, want STELLANTIS", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCapture verifies that XHR captures are parsed and upserted into
// the KG when the mock browser returns the fixture body.
func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "stellantis_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://peugeot-test.example/api/dealers?zip=75001",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := stellantis.NewWithURLs(graph, mb, testBrandURLs("https://peugeot-test.example/trouver-un-concessionnaire.html"))

	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if len(graph.dealers) != 2 {
		t.Errorf("upserted dealers = %d, want 2", len(graph.dealers))
	}

	// Identifiers should carry the "peugeot:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if !startsWith(id.IdentifierValue, "peugeot:") {
				t.Errorf("OEM_DEALER_ID %q missing peugeot: prefix", id.IdentifierValue)
			}
		}
	}
}

// TestRun_NilBrowser returns an empty result when the browser is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := stellantis.New(graph, nil)
	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}

// TestRun_NoXHRCaptures returns zero counts when the mock browser returns no
// captures (simulates SPA that requires form interaction).
func TestRun_NoXHRCaptures(t *testing.T) {
	mb := &mockBrowser{xhrCaptures: nil}
	graph := &recordingGraph{}
	loc := stellantis.NewWithURLs(graph, mb, testBrandURLs("https://peugeot-test.example/trouver-un-concessionnaire.html"))

	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR, got %d", result.Discovered)
	}
}

// TestRun_Deduplication verifies that the same dealer returned across multiple
// postcode sweeps is counted only once.
func TestRun_Deduplication(t *testing.T) {
	singleDealerBody := []byte(`{"dealers":[{
		"id":"FR-PEU-99999",
		"name":"Peugeot Paris Partout",
		"address":{"street":"1 Rue Test","postalCode":"75001","city":"Paris","countryCode":"FR"}
	}]}`)

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{RequestURL: "https://peugeot-test.example/api", ResponseStatus: 200, ResponseBody: singleDealerBody},
		},
	}
	graph := &recordingGraph{}
	loc := stellantis.NewWithURLs(graph, mb, testBrandURLs("https://peugeot-test.example/trouver-un-concessionnaire.html"))

	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// 10 postcodes swept, same dealer returned each time → 1 discovered.
	if result.Discovered != 1 {
		t.Errorf("expected 1 discovered (deduplication), got %d", result.Discovered)
	}
}

// ── small helpers ─────────────────────────────────────────────────────────────

func startsWith(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}
