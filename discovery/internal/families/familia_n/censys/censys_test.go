package censys_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/discovery/internal/families/familia_n/censys"
	"cardex.eu/discovery/internal/kg"
)

// stubGraph satisfies the kg.KnowledgeGraph interface for testing.
type stubGraph struct {
	kg.KnowledgeGraph
	presences   []*kg.DealerWebPresence
	identifiers []*kg.DealerIdentifier
	existing    map[string]string // identifierValue -> dealerID
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

func TestRun_SkipWhenNoCredentials(t *testing.T) {
	graph := &stubGraph{}
	c := censys.New(graph, "", "")
	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
}

func TestRun_StoresHostForDomain(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/api/v2/hosts/search") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":   200,
			"status": "OK",
			"result": map[string]any{
				"total": 1,
				"hits":  []map[string]any{{"ip": "1.2.3.4"}},
			},
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "autohaus-test.de"},
		},
		existing: map[string]string{},
	}
	c := censys.NewWithClient(graph, "id1", "sec1", srv.URL, srv.Client())

	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.identifiers) != 1 {
		t.Fatalf("want 1 identifier stored, got %d", len(graph.identifiers))
	}
	if graph.identifiers[0].IdentifierValue != "1.2.3.4" {
		t.Errorf("want IP 1.2.3.4, got %s", graph.identifiers[0].IdentifierValue)
	}
	if graph.identifiers[0].IdentifierType != kg.IdentifierCensysHostID {
		t.Errorf("want type CENSYS_HOST_ID, got %s", graph.identifiers[0].IdentifierType)
	}
}

func TestRun_HTTP429_CountsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.de"},
		},
	}
	c := censys.NewWithClient(graph, "id1", "sec1", srv.URL, srv.Client())

	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 1 {
		t.Errorf("want 1 error counted, got %d", result.Errors)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
}

func TestRun_SkipAlreadyKnownHost(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":   200,
			"status": "OK",
			"result": map[string]any{
				"total": 1,
				"hits":  []map[string]any{{"ip": "5.6.7.8"}},
			},
		})
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "example.de"},
		},
		// IP already stored in KG
		existing: map[string]string{"5.6.7.8": "D2"},
	}
	c := censys.NewWithClient(graph, "id1", "sec1", srv.URL, srv.Client())

	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered (already known), got %d", result.Discovered)
	}
}
