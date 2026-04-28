package hyundai_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/hyundai"
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
		"HYUNDAI": {"DE": locatorURL},
	}
}

// ── ParseCapture ──────────────────────────────────────────────────────────────

func TestParseCapture(t *testing.T) {
	fixture := mustReadFixture(t, "hyundai_dealer_api.json")
	dealers, err := hyundai.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer uses "id" field.
	d0 := dealers[0]
	if d0.CanonicalID() != "DE-HYU-401" {
		t.Errorf("dealers[0].CanonicalID() = %q, want DE-HYU-401", d0.CanonicalID())
	}
	if d0.CanonicalName() != "Hyundai Berlin Mitte" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}
	if d0.PostalCode() != "10707" {
		t.Errorf("dealers[0].PostalCode() = %q, want 10707", d0.PostalCode())
	}
	if d0.CountryCode() != "DE" {
		t.Errorf("dealers[0].CountryCode() = %q, want DE", d0.CountryCode())
	}

	// Second dealer uses "dealerCode" field and "zipCode" address field.
	d1 := dealers[1]
	if d1.CanonicalID() != "DE-KIA-402" {
		t.Errorf("dealers[1].CanonicalID() = %q, want DE-KIA-402", d1.CanonicalID())
	}
	if d1.PostalCode() != "10119" {
		t.Errorf("dealers[1].PostalCode() = %q, want 10119", d1.PostalCode())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := hyundai.New(nil, nil)
	if loc.OEMID() != "HYUNDAI" {
		t.Errorf("OEMID = %q, want HYUNDAI", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "hyundai_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://www.hyundai.de/api/dealers?zip=10115",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := hyundai.NewWithURLs(graph, mb, testBrandURLs("https://www.hyundai.de/haendlersuche"))

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

	// OEM_DEALER_ID identifiers should have "hyundai:" prefix.
	for _, id := range graph.identifiers {
		if id.IdentifierType == kg.IdentifierOEMDealerID {
			if len(id.IdentifierValue) < 8 || id.IdentifierValue[:8] != "hyundai:" {
				t.Errorf("OEM_DEALER_ID %q missing hyundai: prefix", id.IdentifierValue)
			}
		}
	}
}

func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := hyundai.New(graph, nil)
	result, err := loc.Run(context.Background(), "DE")
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
	loc := hyundai.NewWithURLs(graph, mb, testBrandURLs("https://www.hyundai.de/haendlersuche"))

	result, err := loc.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR captures, got %d", result.Discovered)
	}
}
