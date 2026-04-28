package toyota_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/toyota"
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

func testBrandURLs(locatorURL string) map[string]map[string]string {
	return map[string]map[string]string{
		"TOYOTA": {"NL": locatorURL},
	}
}

// ── ParseCapture ──────────────────────────────────────────────────────────────

// TestParseCapture_NestedResult verifies the result.dealers nested envelope.
func TestParseCapture_NestedResult(t *testing.T) {
	fixture := mustReadFixture(t, "toyota_dealer_api.json")
	dealers, err := toyota.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer uses "id" field.
	d0 := dealers[0]
	if d0.CanonicalID() != "NL-TOY-301" {
		t.Errorf("dealers[0].CanonicalID() = %q, want NL-TOY-301", d0.CanonicalID())
	}
	if d0.CanonicalName() != "Toyota Amsterdam" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}
	if d0.CountryCode() != "NL" {
		t.Errorf("dealers[0].CountryCode() = %q, want NL", d0.CountryCode())
	}

	// Second dealer uses "dealerId" field and "zipCode" address field.
	d1 := dealers[1]
	if d1.CanonicalID() != "NL-TOY-302" {
		t.Errorf("dealers[1].CanonicalID() = %q, want NL-TOY-302", d1.CanonicalID())
	}
	if d1.PostalCode() != "3532 AD" {
		t.Errorf("dealers[1].PostalCode() = %q, want 3532 AD", d1.PostalCode())
	}
}

// TestParseCapture_FlatEnvelope verifies that standard flat {"dealers":[...]} also works.
func TestParseCapture_FlatEnvelope(t *testing.T) {
	body := []byte(`{"dealers":[
		{"id":"NL-TOY-999","name":"Toyota Test","address":{"postalCode":"1011","city":"Amsterdam","countryCode":"NL"}},
		{"dealerId":"NL-LEX-888","name":"Lexus Test","address":{"postalCode":"3011","city":"Rotterdam","countryCode":"NL"}}
	]}`)
	dealers, err := toyota.ParseCapture(body)
	if err != nil {
		t.Fatalf("ParseCapture flat: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers from flat envelope, got %d", len(dealers))
	}
	if dealers[0].CanonicalID() != "NL-TOY-999" {
		t.Errorf("dealers[0].CanonicalID() = %q, want NL-TOY-999", dealers[0].CanonicalID())
	}
	if dealers[1].CanonicalID() != "NL-LEX-888" {
		t.Errorf("dealers[1].CanonicalID() = %q, want NL-LEX-888", dealers[1].CanonicalID())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := toyota.New(nil, nil)
	if loc.OEMID() != "TOYOTA" {
		t.Errorf("OEMID = %q, want TOYOTA", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "toyota_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://www.toyota.nl/api/dealers?zip=1011",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := toyota.NewWithURLs(graph, mb, testBrandURLs("https://www.toyota.nl/dealer-zoeken"))

	result, err := loc.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if len(graph.dealers) != 2 {
		t.Errorf("upserted dealers = %d, want 2", len(graph.dealers))
	}

	// OEM_DEALER_ID identifiers should have "toyota:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if len(id.IdentifierValue) < 7 || id.IdentifierValue[:7] != "toyota:" {
				t.Errorf("OEM_DEALER_ID %q missing toyota: prefix", id.IdentifierValue)
			}
		}
	}
}

func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := toyota.New(graph, nil)
	result, err := loc.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered with nil browser, got %d", result.Discovered)
	}
}

func TestRun_NoXHRCaptures(t *testing.T) {
	mb := &mockBrowser{xhrCaptures: nil}
	graph := &recordingGraph{}
	loc := toyota.NewWithURLs(graph, mb, testBrandURLs("https://www.toyota.nl/dealer-zoeken"))

	result, err := loc.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR captures, got %d", result.Discovered)
	}
}
