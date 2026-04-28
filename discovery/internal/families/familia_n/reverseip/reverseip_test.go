package reverseip_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_n/reverseip"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	presences []*kg.DealerWebPresence
	known     map[string]string // domain -> dealerID (existing)
	upserted  []*kg.DealerWebPresence
}

func (g *stubGraph) ListWebPresencesForInfraScan(_ context.Context, _ string, _ int) ([]*kg.DealerWebPresence, error) {
	return g.presences, nil
}
func (g *stubGraph) FindDealerIDByDomain(_ context.Context, domain string) (string, error) {
	if g.known != nil {
		return g.known[domain], nil
	}
	return "", nil
}
func (g *stubGraph) UpsertWebPresence(_ context.Context, wp *kg.DealerWebPresence) error {
	g.upserted = append(g.upserted, wp)
	return nil
}

func TestRun_SkipWhenNoAPIKey(t *testing.T) {
	graph := &stubGraph{}
	r := reverseip.New(graph, "")
	result, err := r.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
}

func TestRun_CohostedDomainUpserted(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"query": "autohaus-test.nl",
			"response": map[string]any{
				"domain_count": "2",
				"domains": []map[string]any{
					{"name": "autohaus-test.nl"},   // same domain -- skip
					{"name": "cohosted-garage.nl"}, // new cohosted domain
				},
			},
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "autohaus-test.nl"},
		},
		known: map[string]string{
			"autohaus-test.nl": "D1", // already in KG
		},
	}
	r := reverseip.NewWithClient(graph, "key123", srv.URL, srv.Client())

	result, err := r.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.upserted) != 1 {
		t.Fatalf("want 1 upserted, got %d", len(graph.upserted))
	}
	if graph.upserted[0].Domain != "cohosted-garage.nl" {
		t.Errorf("unexpected domain: %s", graph.upserted[0].Domain)
	}
}

func TestRun_HTTP429_CountsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.nl"},
		},
	}
	r := reverseip.NewWithClient(graph, "key123", srv.URL, srv.Client())

	result, err := r.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 1 {
		t.Errorf("want 1 error counted, got %d", result.Errors)
	}
}

func TestRun_SkipsAlreadyKnownCohostedDomain(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"query": "example.nl",
			"response": map[string]any{
				"domain_count": "1",
				"domains": []map[string]any{
					{"name": "already-known.nl"},
				},
			},
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.nl"},
		},
		known: map[string]string{"already-known.nl": "D2"},
	}
	r := reverseip.NewWithClient(graph, "key123", srv.URL, srv.Client())

	result, err := r.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 (already known), got %d", result.Discovered)
	}
}
