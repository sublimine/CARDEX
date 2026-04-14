package ford_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/ford"
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

// ── ParseCapture ──────────────────────────────────────────────────────────────

// TestParseCapture_DealersEnvelope verifies that ParseCapture handles the
// standard "dealers" JSON envelope and reads both "id" and "dealerId" field
// variants correctly.
func TestParseCapture_DealersEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "ford_dealer_api.json")
	dealers, err := ford.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer: id field.
	d0 := dealers[0]
	if got := d0.CanonicalID(); got != "DE-FRD-601" {
		t.Errorf("dealers[0].CanonicalID() = %q, want DE-FRD-601", got)
	}
	if d0.CanonicalName() != "Ford Berlin Tempelhof" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}
	if d0.PostalCode() != "12099" {
		t.Errorf("dealers[0].PostalCode() = %q", d0.PostalCode())
	}
	if d0.CountryCode() != "DE" {
		t.Errorf("dealers[0].CountryCode() = %q", d0.CountryCode())
	}

	// Second dealer: dealerId field (alternate ID).
	d1 := dealers[1]
	if got := d1.CanonicalID(); got != "DE-FRD-602" {
		t.Errorf("dealers[1].CanonicalID() = %q, want DE-FRD-602", got)
	}
	if d1.CanonicalName() != "Ford Berlin Mitte" {
		t.Errorf("dealers[1].CanonicalName() = %q", d1.CanonicalName())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := ford.New(nil, nil)
	if loc.OEMID() != "FORD" {
		t.Errorf("OEMID = %q, want FORD", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCapture verifies that captured XHR responses are parsed and
// upserted into the KG.
func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "ford_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://www.ford-test.example/api/dealers?zip=10115",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	locatorURL := "https://www.ford-test.example/haendlersuche"
	testURLs := map[string]map[string]string{
		"FORD": {"DE": locatorURL},
	}
	loc := ford.NewWithURLs(graph, mb, testURLs)

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

	// OEM_DEALER_ID identifiers should have "ford:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if len(id.IdentifierValue) < 5 || id.IdentifierValue[:5] != "ford:" {
				t.Errorf("OEM_DEALER_ID %q missing ford: prefix", id.IdentifierValue)
			}
		}
	}
}

// TestRun_NilBrowser returns an empty result without error when the browser
// is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := ford.New(graph, nil)
	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered with nil browser, got %d", result.Discovered)
	}
}

// TestRun_NoXHRCaptures returns an empty result without error when the mock
// browser returns no XHR captures.
func TestRun_NoXHRCaptures(t *testing.T) {
	mb := &mockBrowser{xhrCaptures: nil}
	graph := &recordingGraph{}
	locatorURL := "https://www.ford-test.example/haendlersuche"
	testURLs := map[string]map[string]string{
		"FORD": {"DE": locatorURL},
	}
	loc := ford.NewWithURLs(graph, mb, testURLs)

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR captures, got %d", result.Discovered)
	}
}
