package shodan_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_n/shodan"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	presences   []*kg.DealerWebPresence
	identifiers []*kg.DealerIdentifier
	existing    map[string]string
}

func (g *stubGraph) ListWebPresencesForInfraScan(_ context.Context, _ string, _ int) ([]*kg.DealerWebPresence, error) {
	return g.presences, nil
}
func (g *stubGraph) FindDealerByIdentifier(_ context.Context, _ kg.IdentifierType, val string) (string, error) {
	return g.existing[val], nil
}
func (g *stubGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	g.identifiers = append(g.identifiers, id)
	return nil
}

func TestRun_SkipWhenNoAPIKey(t *testing.T) {
	graph := &stubGraph{}
	s := shodan.New(graph, "")
	result, err := s.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
}

func TestRun_StoresHostForDomain(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"total": 1,
			"matches": []map[string]any{
				{"ip_str": "10.0.0.1", "hostnames": []string{"autohaus.fr"}, "port": 443},
			},
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "autohaus.fr"},
		},
		existing: map[string]string{},
	}
	s := shodan.NewWithClient(graph, "key123", srv.URL, srv.Client())

	result, err := s.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.identifiers) != 1 {
		t.Fatalf("want 1 identifier, got %d", len(graph.identifiers))
	}
	if graph.identifiers[0].IdentifierValue != "10.0.0.1" {
		t.Errorf("want IP 10.0.0.1, got %s", graph.identifiers[0].IdentifierValue)
	}
	if graph.identifiers[0].IdentifierType != kg.IdentifierShodanHostID {
		t.Errorf("want type SHODAN_HOST_ID, got %s", graph.identifiers[0].IdentifierType)
	}
}

func TestRun_HTTP429_CountsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.fr"},
		},
	}
	s := shodan.NewWithClient(graph, "key123", srv.URL, srv.Client())

	result, err := s.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 1 {
		t.Errorf("want 1 error counted, got %d", result.Errors)
	}
}

func TestRun_ShodanAPIError_CountsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error": "Invalid API key.",
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.fr"},
		},
	}
	s := shodan.NewWithClient(graph, "badkey", srv.URL, srv.Client())

	result, err := s.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 1 {
		t.Errorf("want 1 error counted, got %d", result.Errors)
	}
}
