package mobilians_test

import (
	"context"
	"os"
	"testing"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_g/mobilians"
	"cardex.eu/discovery/internal/kg"
)

// ── mock browser ──────────────────────────────────────────────────────────────

type mockBrowser struct {
	xhrCaptures []*browser.XHRCapture
	xhrErr      error
	fetchResult *browser.FetchResult
	fetchErr    error
}

func (m *mockBrowser) FetchHTML(_ context.Context, _ string, _ *browser.FetchOptions) (*browser.FetchResult, error) {
	return m.fetchResult, m.fetchErr
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
	dealers []*kg.DealerEntity
}

func (r *recordingGraph) FindDealerByIdentifier(_ context.Context, _ kg.IdentifierType, _ string) (string, error) {
	return "", nil
}
func (r *recordingGraph) UpsertDealer(_ context.Context, e *kg.DealerEntity) error {
	r.dealers = append(r.dealers, e)
	return nil
}
func (r *recordingGraph) AddIdentifier(_ context.Context, _ *kg.DealerIdentifier) error { return nil }
func (r *recordingGraph) AddLocation(_ context.Context, _ *kg.DealerLocation) error     { return nil }
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

// ── ParseMembersJSON ──────────────────────────────────────────────────────────

// TestParseMembersJSON_HitsEnvelope verifies parsing of the "hits" envelope.
func TestParseMembersJSON_HitsEnvelope(t *testing.T) {
	fixture := mustReadFixture(t, "mobilians_members_api.json")
	members, err := mobilians.ParseMembersJSON(fixture)
	if err != nil {
		t.Fatalf("ParseMembersJSON: %v", err)
	}
	if len(members) != 2 {
		t.Fatalf("want 2 members, got %d", len(members))
	}

	m0 := members[0]
	if m0.ID != "MOB-001" {
		t.Errorf("members[0].ID = %q, want MOB-001", m0.ID)
	}
	if m0.Name != "Garage Dupont SA" {
		t.Errorf("members[0].Name = %q", m0.Name)
	}
	if m0.Zip != "75001" {
		t.Errorf("members[0].Zip = %q", m0.Zip)
	}
	if m0.City != "Paris" {
		t.Errorf("members[0].City = %q", m0.City)
	}
	if m0.Phone != "01 23 45 67 89" {
		t.Errorf("members[0].Phone = %q", m0.Phone)
	}
}

// TestParseMembersJSON_AlternativeEnvelopes verifies results/items/data/bare-array.
func TestParseMembersJSON_AlternativeEnvelopes(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{"results", `{"results":[{"id":"R1","title":"Result Garage","zip":"75002","city":"Paris"}]}`},
		{"items", `{"items":[{"id":"I1","name":"Item Garage","zip":"69001","city":"Lyon"}]}`},
		{"data", `{"data":[{"id":"D1","title":"Data Garage","zip":"13001","city":"Marseille"}]}`},
		{"array", `[{"id":"A1","title":"Array Garage","zip":"31000","city":"Toulouse"}]`},
	}
	for _, tc := range cases {
		members, err := mobilians.ParseMembersJSON([]byte(tc.body))
		if err != nil {
			t.Errorf("%s: unexpected error: %v", tc.name, err)
			continue
		}
		if len(members) != 1 {
			t.Errorf("%s: want 1 member, got %d", tc.name, len(members))
		}
	}
}

// TestParseMembersJSON_NameFallback verifies that "name" field is used when "title" is empty.
func TestParseMembersJSON_NameFallback(t *testing.T) {
	body := `{"hits":[{"id":"X1","name":"Garage Name Field","zip":"06000","city":"Nice"}]}`
	members, err := mobilians.ParseMembersJSON([]byte(body))
	if err != nil {
		t.Fatalf("ParseMembersJSON: %v", err)
	}
	if len(members) != 1 {
		t.Fatalf("want 1 member, got %d", len(members))
	}
	if members[0].Name != "Garage Name Field" {
		t.Errorf("Name = %q, want 'Garage Name Field'", members[0].Name)
	}
}

// TestParseMembersJSON_Empty returns nil for empty body.
func TestParseMembersJSON_Empty(t *testing.T) {
	members, err := mobilians.ParseMembersJSON(nil)
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if len(members) != 0 {
		t.Errorf("expected empty, got %v", members)
	}
}

// ── ParseMembersHTML ──────────────────────────────────────────────────────────

// TestParseMembersHTML_Fixture parses the YOOtheme/Joomla member-card fixture.
func TestParseMembersHTML_Fixture(t *testing.T) {
	fixture := string(mustReadFixture(t, "mobilians_annuaire.html"))
	members := mobilians.ParseMembersHTML(fixture)

	if len(members) < 2 {
		t.Fatalf("want at least 2 members, got %d", len(members))
	}

	names := map[string]bool{}
	for _, m := range members {
		names[m.Name] = true
	}
	if !names["Garage Dupont SA"] {
		t.Errorf("expected 'Garage Dupont SA' in parsed members; got %v", membersNames(members))
	}
	if !names["Auto Centre Lyon"] {
		t.Errorf("expected 'Auto Centre Lyon' in parsed members; got %v", membersNames(members))
	}
}

// TestParseMembersHTML_EmptyPage returns empty slice for page with no cards.
func TestParseMembersHTML_EmptyPage(t *testing.T) {
	members := mobilians.ParseMembersHTML(`<html><body><p>Aucun membre.</p></body></html>`)
	if len(members) != 0 {
		t.Errorf("expected empty, got %v", members)
	}
}

func membersNames(members []mobilians.MobiliansMember) []string {
	names := make([]string, len(members))
	for i, m := range members {
		names[i] = m.Name
	}
	return names
}

// ── Run ───────────────────────────────────────────────────────────────────────

// TestRun_XHRCapture verifies that XHR-captured JSON is parsed and upserted.
func TestRun_XHRCapture(t *testing.T) {
	fixture := mustReadFixture(t, "mobilians_members_api.json")

	mb := &mockBrowser{
		xhrCaptures: []*browser.XHRCapture{
			{
				RequestURL:     "https://mobilians.fr/libraries/search_es.php?type=json",
				ResponseStatus: 200,
				ResponseBody:   fixture,
			},
		},
	}

	graph := &recordingGraph{}
	loc := mobilians.NewWithBaseURL(graph, mb, "https://mobilians.fr")

	result, err := loc.Run(context.Background())
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

// TestRun_FetchHTMLFallback verifies that when XHR yields nothing,
// FetchHTML fallback parses the rendered HTML.
func TestRun_FetchHTMLFallback(t *testing.T) {
	fixture := string(mustReadFixture(t, "mobilians_annuaire.html"))

	mb := &mockBrowser{
		xhrCaptures: nil, // Phase 1 yields nothing
		fetchResult: &browser.FetchResult{
			HTML:       fixture,
			StatusCode: 200,
		},
	}

	graph := &recordingGraph{}
	loc := mobilians.NewWithBaseURL(graph, mb, "https://mobilians.fr")

	result, err := loc.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered == 0 {
		t.Errorf("expected >0 discovered from FetchHTML fallback, got 0")
	}
}

// TestRun_NilBrowser returns empty result when browser is nil.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	loc := mobilians.New(graph, nil)

	result, err := loc.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}

// TestRun_EmptyXHRAndEmptyHTML verifies 0 discovered when no data available.
func TestRun_EmptyXHRAndEmptyHTML(t *testing.T) {
	mb := &mockBrowser{
		xhrCaptures: nil,
		fetchResult: &browser.FetchResult{
			HTML:       `<html><body><p>Annuaire temporairement indisponible.</p></body></html>`,
			StatusCode: 200,
		},
	}

	graph := &recordingGraph{}
	loc := mobilians.NewWithBaseURL(graph, mb, "https://mobilians.fr")

	result, err := loc.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}
