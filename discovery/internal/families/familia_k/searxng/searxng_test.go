package searxng_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_k/searxng"
	"cardex.eu/discovery/internal/kg"
)

// ── KG stub ───────────────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	knownDomains   map[string]string // domain → dealerID
	upsertedDomains []string
	discoveries    int
	states         map[string]string
	upsertedDealers []string
	addedIdentifiers []string
}

func newStubGraph(known map[string]string) *stubGraph {
	if known == nil {
		known = map[string]string{}
	}
	return &stubGraph{
		knownDomains: known,
		states:       map[string]string{},
	}
}

func (g *stubGraph) FindDealerIDByDomain(_ context.Context, domain string) (string, error) {
	return g.knownDomains[domain], nil
}
func (g *stubGraph) FindDealerByIdentifier(_ context.Context, _ kg.IdentifierType, _ string) (string, error) {
	return "", nil
}
func (g *stubGraph) UpsertDealer(_ context.Context, d *kg.DealerEntity) error {
	g.upsertedDealers = append(g.upsertedDealers, d.CanonicalName)
	return nil
}
func (g *stubGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	g.addedIdentifiers = append(g.addedIdentifiers, id.IdentifierValue)
	return nil
}
func (g *stubGraph) UpsertWebPresence(_ context.Context, wp *kg.DealerWebPresence) error {
	g.upsertedDomains = append(g.upsertedDomains, wp.Domain)
	return nil
}
func (g *stubGraph) RecordDiscovery(_ context.Context, _ *kg.DiscoveryRecord) error {
	g.discoveries++
	return nil
}
func (g *stubGraph) GetProcessingState(_ context.Context, _ string) (string, error) { return "", nil }
func (g *stubGraph) SetProcessingState(_ context.Context, _, _ string) error        { return nil }
func (g *stubGraph) AddLocation(_ context.Context, _ *kg.DealerLocation) error     { return nil }
func (g *stubGraph) UpdateConfidenceScore(_ context.Context, _ string, _ float64) error {
	return nil
}
func (g *stubGraph) FindDealersForVATValidation(_ context.Context, _ []string, _ int) ([]*kg.DealerVATCandidate, error) {
	return nil, nil
}
func (g *stubGraph) UpdateVATValidation(_ context.Context, _ string, _ time.Time, _ string) error {
	return nil
}
func (g *stubGraph) UpdateWebPresenceMetadata(_ context.Context, _, _ string) error { return nil }
func (g *stubGraph) ListWebPresencesByCountry(_ context.Context, _ string) ([]*kg.DealerWebPresence, error) {
	return nil, nil
}

// ── SearXNG mock server ───────────────────────────────────────────────────────

func mockSearXNGServer(t *testing.T, results []map[string]interface{}) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/search") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"query":             r.URL.Query().Get("q"),
			"number_of_results": len(results),
			"results":           results,
		})
	}))
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestRun_ConfirmsKnownDomain(t *testing.T) {
	// Result URL matches a known domain in the KG.
	srv := mockSearXNGServer(t, []map[string]interface{}{
		{"url": "https://www.autohaus-schmidt.de/fahrzeuge", "title": "Autohaus Schmidt", "score": 1.0},
	})
	defer srv.Close()

	graph := newStubGraph(map[string]string{
		"autohaus-schmidt.de": "DEALER-001",
	})
	s := searxng.NewWithConfig(graph, []string{srv.URL}, 0)

	result, err := s.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("want 0 errors, got %d", result.Errors)
	}
	if result.Confirmed != 10 { // 10 query templates × 1 known result each
		t.Errorf("want 10 confirmations (1 per query), got %d", result.Confirmed)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered (domain known), got %d", result.Discovered)
	}
}

func TestRun_DiscoversNewDomain(t *testing.T) {
	srv := mockSearXNGServer(t, []map[string]interface{}{
		{"url": "https://www.newdealer.de", "title": "New Dealer", "score": 0.8},
	})
	defer srv.Close()

	graph := newStubGraph(nil) // no known domains
	s := searxng.NewWithConfig(graph, []string{srv.URL}, 0)

	result, err := s.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered == 0 {
		t.Error("want at least 1 discovered new domain")
	}
	if len(graph.upsertedDealers) == 0 {
		t.Error("want at least 1 upserted dealer entity for new domain")
	}
}

func TestRun_SkipsEmptyDomain(t *testing.T) {
	srv := mockSearXNGServer(t, []map[string]interface{}{
		{"url": "not-a-url", "title": "Bad URL", "score": 0.5},
		{"url": "", "title": "Empty URL", "score": 0.1},
	})
	defer srv.Close()

	graph := newStubGraph(nil)
	s := searxng.NewWithConfig(graph, []string{srv.URL}, 0)

	result, err := s.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 && result.Confirmed != 0 {
		t.Errorf("want 0 results for bad URLs, got disc=%d conf=%d",
			result.Discovered, result.Confirmed)
	}
}

func TestRun_UnsupportedCountry(t *testing.T) {
	graph := newStubGraph(nil)
	s := searxng.NewWithConfig(graph, []string{"http://localhost:0"}, 0)

	result, err := s.Run(context.Background(), "ZZ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Unsupported country returns empty result without error.
	if result.Discovered != 0 || result.Confirmed != 0 {
		t.Errorf("want empty result for unsupported country")
	}
}
