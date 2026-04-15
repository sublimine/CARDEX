package gdelt_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_o/gdelt"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	upserted    []*kg.DealerEntity
	discoveries []*kg.DiscoveryRecord
	signals     []*kg.DealerPressSignal
	nameMap     map[string][]string // normalizedName -> []dealerID
}

func (g *stubGraph) FindDealersByName(_ context.Context, norm, _ string) ([]string, error) {
	if g.nameMap != nil {
		return g.nameMap[norm], nil
	}
	return nil, nil
}
func (g *stubGraph) UpsertDealer(_ context.Context, e *kg.DealerEntity) error {
	g.upserted = append(g.upserted, e)
	return nil
}
func (g *stubGraph) RecordDiscovery(_ context.Context, r *kg.DiscoveryRecord) error {
	g.discoveries = append(g.discoveries, r)
	return nil
}
func (g *stubGraph) RecordPressSignal(_ context.Context, s *kg.DealerPressSignal) error {
	g.signals = append(g.signals, s)
	return nil
}

func TestRun_UnsupportedCountry(t *testing.T) {
	graph := &stubGraph{}
	c := gdelt.New(graph)
	result, err := c.Run(context.Background(), "PL") // not in gdeltCountry map
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0, got %d", result.Discovered)
	}
}

func TestRun_CreatesLowConfidenceCandidate(t *testing.T) {
	// Mock server: GDELT returns 1 article; article contains "Autohaus Muster GmbH"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/v2/doc/doc":
			// GDELT article list
			_ = json.NewEncoder(w).Encode(map[string]any{
				"articles": []map[string]any{
					{
						"url":   "http://" + r.Host + "/article",
						"title": "Autohaus Muster GmbH eröffnet neue Filiale",
					},
				},
			})
		case r.URL.Path == "/article":
			// Article HTML
			_, _ = w.Write([]byte(`<html><body>
<p>Der Automobilhändler Autohaus Muster GmbH hat heute eine neue Filiale in Berlin eröffnet.</p>
</body></html>`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	graph := &stubGraph{} // no known dealers
	c := gdelt.NewWithClient(graph, srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered == 0 {
		t.Error("want at least 1 discovered candidate")
	}
	if len(graph.upserted) == 0 {
		t.Error("want at least 1 upserted dealer")
	}
}

func TestRun_RecordsDiscoveryForExistingDealer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/v2/doc/doc":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"articles": []map[string]any{
					{
						"url":   "http://" + r.Host + "/article",
						"title": "Garage Dupont SARL ouvre un nouveau centre",
					},
				},
			})
		case r.URL.Path == "/article":
			_, _ = w.Write([]byte(`<html><body>
<p>Garage Dupont SARL a ouvert un nouveau centre automobile à Paris.</p>
</body></html>`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	graph := &stubGraph{
		nameMap: map[string][]string{
			"dupont": {"D1"}, // existing dealer
		},
	}
	c := gdelt.NewWithClient(graph, srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := c.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Discovered = 0 because dealer already exists
	if result.Discovered != 0 {
		t.Errorf("want 0 (dealer known), got %d", result.Discovered)
	}
	// But RecordDiscovery should have been called
	if len(graph.discoveries) == 0 {
		t.Error("want at least 1 RecordDiscovery call for existing dealer")
	}
	if len(graph.signals) == 0 {
		t.Error("want at least 1 RecordPressSignal call")
	}
}

func TestRun_GDELT_HTTP_Error(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	graph := &stubGraph{}
	c := gdelt.NewWithClient(graph, srv.URL, &http.Client{Timeout: 5 * time.Second})

	_, err := c.Run(context.Background(), "DE")
	if err == nil {
		t.Error("want error on GDELT 503, got nil")
	}
}
