package bmw_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/bmw"
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
// Only BMW/DE is populated so tests run a single brand sweep.
func testBrandURLs(locatorURL string) map[string]map[string]string {
	return map[string]map[string]string{
		"BMW": {"DE": locatorURL},
	}
}

// ── ParseCapture ──────────────────────────────────────────────────────────────

// TestParseCapture_DealersEnvelope verifies "dealers" JSON envelope parsing
// using the bmw_dealer_api.json fixture.
func TestParseCapture_DealersEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "bmw_dealer_api.json")
	dealers, err := bmw.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer uses "id" field.
	d0 := dealers[0]
	if d0.CanonicalID() != "DE-BMW-101" {
		t.Errorf("dealers[0].CanonicalID() = %q, want DE-BMW-101", d0.CanonicalID())
	}
	if d0.CanonicalName() != "BMW München Zentrum" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}

	// Second dealer uses "code" field.
	d1 := dealers[1]
	if d1.CanonicalID() != "DE-BMW-102" {
		t.Errorf("dealers[1].CanonicalID() = %q, want DE-BMW-102", d1.CanonicalID())
	}
	if d1.CanonicalName() != "BMW München Nord" {
		t.Errorf("dealers[1].CanonicalName() = %q", d1.CanonicalName())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := bmw.New(nil, nil)
	if loc.OEMID() != "BMW" {
		t.Errorf("OEMID = %q, want BMW", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCapture verifies that XHR captures are parsed and upserted into
// the KG when the mock browser returns the fixture body.
func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "bmw_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://bmw-test.example/api/retailers?zip=80539",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := bmw.NewWithURLs(graph, mb, testBrandURLs("https://bmw-test.example/de/dealer-locator.html"))

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

	// Identifiers should carry the "bmw:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if !startsWith(id.IdentifierValue, "bmw:") {
				t.Errorf("OEM_DEALER_ID %q missing bmw: prefix", id.IdentifierValue)
			}
		}
	}
}

// TestRun_NilBrowser returns an empty result when the browser is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := bmw.New(graph, nil)
	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}

// TestRun_NoXHRCaptures returns zero counts when the mock browser returns no
// captures (simulates SPA that requires form interaction or DDoS challenge).
func TestRun_NoXHRCaptures(t *testing.T) {
	mb := &mockBrowser{xhrCaptures: nil}
	graph := &recordingGraph{}
	loc := bmw.NewWithURLs(graph, mb, testBrandURLs("https://bmw-test.example/de/dealer-locator.html"))

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR, got %d", result.Discovered)
	}
}

// ── small helpers ─────────────────────────────────────────────────────────────

func startsWith(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}
