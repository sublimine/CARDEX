package renault_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/renault"
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

// TestParseCapture_DealershipsEnvelope verifies that ParseCapture handles the
// "dealerships" JSON envelope used by Renault Group APIs, and reads both the
// "id" and "siteId" field variants correctly.
func TestParseCapture_DealershipsEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "renault_dealer_api.json")
	dealers, err := renault.ParseCapture(fixture)
	if err != nil {
		t.Fatalf("ParseCapture: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2 dealers, got %d", len(dealers))
	}

	// First dealer: id field.
	d0 := dealers[0]
	if got := d0.CanonicalID(); got != "FR-REN-501" {
		t.Errorf("dealers[0].CanonicalID() = %q, want FR-REN-501", got)
	}
	if d0.CanonicalName() != "Renault Paris 15ème" {
		t.Errorf("dealers[0].CanonicalName() = %q", d0.CanonicalName())
	}
	if d0.PostalCode() != "75015" {
		t.Errorf("dealers[0].PostalCode() = %q", d0.PostalCode())
	}
	if d0.CountryCode() != "FR" {
		t.Errorf("dealers[0].CountryCode() = %q", d0.CountryCode())
	}

	// Second dealer: siteId field (alternate ID), zipCode field (alternate postal).
	d1 := dealers[1]
	if got := d1.CanonicalID(); got != "FR-DAC-502" {
		t.Errorf("dealers[1].CanonicalID() = %q, want FR-DAC-502", got)
	}
	if d1.CanonicalName() != "Dacia Paris Sud" {
		t.Errorf("dealers[1].CanonicalName() = %q", d1.CanonicalName())
	}
}

// ── OEMID ─────────────────────────────────────────────────────────────────────

func TestOEMID(t *testing.T) {
	loc := renault.New(nil, nil)
	if loc.OEMID() != "RENAULT" {
		t.Errorf("OEMID = %q, want RENAULT", loc.OEMID())
	}
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCapture verifies that captured XHR responses are parsed and
// upserted into the KG.
func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "renault_dealer_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://www.renault-test.example/api/dealerships?zip=75001",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	locatorURL := "https://www.renault-test.example/concessionnaires.html"
	testURLs := map[string]map[string]string{
		"RENAULT": {"FR": locatorURL},
	}
	loc := renault.NewWithURLs(graph, mb, testURLs)

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
}

// TestRun_NilBrowser returns an empty result without error when the browser
// is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := renault.New(graph, nil)
	result, err := loc.Run(context.Background(), "FR")
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
	locatorURL := "https://www.renault-test.example/concessionnaires.html"
	testURLs := map[string]map[string]string{
		"RENAULT": {"FR": locatorURL},
	}
	loc := renault.NewWithURLs(graph, mb, testURLs)

	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 when no XHR captures, got %d", result.Discovered)
	}
}

// TestRun_Deduplication verifies that the same dealer returned from multiple
// postcode sweeps is counted exactly once.
func TestRun_Deduplication(t *testing.T) {
	singleDealerBody := []byte(`{"dealers":[{
		"id":"FR-REN-99999",
		"name":"Same Dealer Everywhere",
		"address":{"street":"Test Rue 1","postalCode":"75001","city":"Paris","countryCode":"FR"}
	}]}`)

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{RequestURL: "http://x/api", ResponseStatus: 200, ResponseBody: singleDealerBody},
		},
	}
	graph := &recordingGraph{}
	locatorURL := "https://www.renault-test.example/concessionnaires.html"
	testURLs := map[string]map[string]string{
		"RENAULT": {"FR": locatorURL},
	}
	loc := renault.NewWithURLs(graph, mb, testURLs)

	result, err := loc.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// 10 postcodes swept for FR, same dealer returned each time → 1 discovered.
	if result.Discovered != 1 {
		t.Errorf("expected 1 discovered (deduplication), got %d", result.Discovered)
	}
}
