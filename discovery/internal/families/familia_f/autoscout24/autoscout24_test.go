package autoscout24_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_f/autoscout24"
	"cardex.eu/discovery/internal/kg"
)

// ── mock browser ──────────────────────────────────────────────────────────────

type mockBrowser struct {
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
	return nil, nil
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
func (r *recordingGraph) RecordDiscovery(_ context.Context, _ *kg.DiscoveryRecord) error {
	return nil
}

// ── helpers ───────────────────────────────────────────────────────────────────

func mustReadFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile("../../../../testdata/" + name)
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}
	return data
}

// ── ParseListingLinks ─────────────────────────────────────────────────────────

// TestParseListingLinks_DE verifies that the German /haendler/ listing fixture
// yields exactly three dealer links and excludes meta-paths.
func TestParseListingLinks_DE(t *testing.T) {
	fixture := string(mustReadFixture(t, "autoscout24_listing.html"))
	links := autoscout24.ParseListingLinks(fixture, "https://www.autoscout24.de", "/haendler/")

	if len(links) != 3 {
		t.Fatalf("want 3 links, got %d: %v", len(links), links)
	}
	for _, link := range links {
		if !strings.HasPrefix(link, "https://www.autoscout24.de/haendler/") {
			t.Errorf("unexpected link: %s", link)
		}
	}
	// Meta-paths must be absent
	for _, link := range links {
		slug := link[strings.LastIndex(link[:len(link)-1], "/")+1 : len(link)-1]
		if slug == "suche" || slug == "hinzufuegen" {
			t.Errorf("meta-slug present in links: %s", slug)
		}
	}
}

// TestParseListingLinks_FR verifies the /concessionnaires/ dirPath.
func TestParseListingLinks_FR(t *testing.T) {
	html := `<html><body>
<a href="/concessionnaires/garage-du-centre-99001/">Garage du Centre</a>
<a href="/concessionnaires/suche/">Recherche</a>
<a href="/concessionnaires/">Tous</a>
<a href="/voitures/audi/">Audi</a>
</body></html>`

	links := autoscout24.ParseListingLinks(html, "https://www.autoscout24.fr", "/concessionnaires/")
	if len(links) != 1 {
		t.Fatalf("want 1 link, got %d: %v", len(links), links)
	}
	if !strings.Contains(links[0], "garage-du-centre-99001") {
		t.Errorf("unexpected link: %s", links[0])
	}
}

// TestParseListingLinks_EmptyPage returns nil for a page with no dealer links.
func TestParseListingLinks_EmptyPage(t *testing.T) {
	html := `<html><body><p>Keine Händler.</p></body></html>`
	links := autoscout24.ParseListingLinks(html, "https://www.autoscout24.de", "/haendler/")
	if len(links) != 0 {
		t.Errorf("expected empty links, got %v", links)
	}
}

// ── ParseDealerProfile ────────────────────────────────────────────────────────

// TestParseDealerProfile verifies __NEXT_DATA__ parsing against the fixture.
func TestParseDealerProfile(t *testing.T) {
	fixture := mustReadFixture(t, "autoscout24_dealer.html")
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(fixture)))
	if err != nil {
		t.Fatalf("goquery: %v", err)
	}
	info, err := autoscout24.ParseDealerProfile(doc)
	if err != nil {
		t.Fatalf("ParseDealerProfile: %v", err)
	}
	if info == nil {
		t.Fatal("nil info")
	}

	checks := []struct{ got, want string }{
		{info.Name, "Autohaus Muster GmbH"},
		{info.ID, "10001"},
		{info.Address.Zip, "10115"},
		{info.Address.City, "Berlin"},
		{info.Contact.Phone, "+49 30 12345678"},
		{info.Contact.Website, "https://www.autohaus-muster.de"},
	}
	for _, c := range checks {
		if c.got != c.want {
			t.Errorf("field: got %q, want %q", c.got, c.want)
		}
	}
}

// TestParseDealerProfile_AlternativeFieldNames verifies accountId/dealerName/
// zipCode/url variants are handled correctly.
func TestParseDealerProfile_AlternativeFieldNames(t *testing.T) {
	html := `<html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"dealerInfoPage":{
  "accountId":"AU-999",
  "dealerName":"Concessionnaire Test",
  "address":{"street":"Rue de la Paix 1","zipCode":"75001","city":"Paris","country":"FR"},
  "contact":{"phone":"+33 1 23456789","url":"https://www.dealer-test.fr"}
}}}}
</script></body></html>`

	doc, _ := goquery.NewDocumentFromReader(strings.NewReader(html))
	info, err := autoscout24.ParseDealerProfile(doc)
	if err != nil {
		t.Fatalf("ParseDealerProfile: %v", err)
	}
	if info == nil {
		t.Fatal("nil info")
	}

	if info.AccountID != "AU-999" {
		t.Errorf("AccountID = %q, want AU-999", info.AccountID)
	}
	if info.DealerName != "Concessionnaire Test" {
		t.Errorf("DealerName = %q", info.DealerName)
	}
	if info.Address.ZipCode != "75001" {
		t.Errorf("ZipCode = %q", info.Address.ZipCode)
	}
	if info.Contact.URL != "https://www.dealer-test.fr" {
		t.Errorf("Contact.URL = %q", info.Contact.URL)
	}
}

// ── Run (full pipeline) ───────────────────────────────────────────────────────

// TestRun_ParseAndUpsert wires a mock browser (returns listing HTML) with an
// httptest server (serves dealer profile pages) and verifies upserts.
func TestRun_ParseAndUpsert(t *testing.T) {
	dealerFixture := mustReadFixture(t, "autoscout24_dealer.html")
	profileSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(dealerFixture)
	}))
	defer profileSrv.Close()

	// Listing fixture has relative hrefs like /haendler/{slug}/
	// FinalURL is the profile server base, so resolution gives profileSrv URLs.
	listingHTML := string(mustReadFixture(t, "autoscout24_listing.html"))

	mb := &mockBrowser{
		fetchResult: &browser.FetchResult{
			HTML:       listingHTML,
			FinalURL:   profileSrv.URL + "/",
			StatusCode: 200,
		},
	}

	graph := &recordingGraph{}
	a := autoscout24.NewWithInterval(graph, mb, 0)
	_, err := a.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(graph.dealers) == 0 {
		t.Fatal("expected dealers upserted, got none")
	}
	found := false
	for _, d := range graph.dealers {
		if d.CanonicalName == "Autohaus Muster GmbH" {
			found = true
		}
	}
	if !found {
		names := make([]string, len(graph.dealers))
		for i, d := range graph.dealers {
			names[i] = d.CanonicalName
		}
		t.Errorf("expected 'Autohaus Muster GmbH' in upserted dealers; got %v", names)
	}
}

// TestRun_UnconfiguredCountry returns empty result for unconfigured ES.
func TestRun_UnconfiguredCountry(t *testing.T) {
	graph := &recordingGraph{}
	a := autoscout24.NewWithInterval(graph, &mockBrowser{}, 0)
	result, err := a.Run(context.Background(), "ES")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0 discovered, got %d", result.Discovered)
	}
}

// TestRun_NilBrowser returns empty result when no browser provided.
func TestRun_NilBrowser(t *testing.T) {
	graph := &recordingGraph{}
	a := autoscout24.NewWithInterval(graph, nil, 0)
	result, err := a.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("expected 0, got %d", result.Discovered)
	}
}
