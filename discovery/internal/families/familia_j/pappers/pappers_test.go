package pappers_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_j/pappers"
	"cardex.eu/discovery/internal/kg"
)

// -- KG stub ------------------------------------------------------------------

type stubGraph struct {
	kg.KnowledgeGraph
	dealers     map[string]*kg.DealerEntity
	identifiers map[string]string // "type:value" -> dealerID
	locations   []*kg.DealerLocation
	state       map[string]string
	confidences map[string]float64
}

func newStub() *stubGraph {
	return &stubGraph{
		dealers:     make(map[string]*kg.DealerEntity),
		identifiers: make(map[string]string),
		state:       make(map[string]string),
		confidences: make(map[string]float64),
	}
}

func (g *stubGraph) FindDealerByIdentifier(_ context.Context, t kg.IdentifierType, v string) (string, error) {
	return g.identifiers[string(t)+":"+v], nil
}
func (g *stubGraph) UpsertDealer(_ context.Context, e *kg.DealerEntity) error {
	g.dealers[e.DealerID] = e
	return nil
}
func (g *stubGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	g.identifiers[string(id.IdentifierType)+":"+id.IdentifierValue] = id.DealerID
	return nil
}
func (g *stubGraph) AddLocation(_ context.Context, loc *kg.DealerLocation) error {
	g.locations = append(g.locations, loc)
	return nil
}
func (g *stubGraph) UpdateConfidenceScore(_ context.Context, id string, score float64) error {
	g.confidences[id] = score
	return nil
}
func (g *stubGraph) GetProcessingState(_ context.Context, key string) (string, error) {
	return g.state[key], nil
}
func (g *stubGraph) SetProcessingState(_ context.Context, key, value string) error {
	g.state[key] = value
	return nil
}

// -- Test server helpers ------------------------------------------------------

func pappersServer(t *testing.T, resp map[string]interface{}) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
}

// -- Tests --------------------------------------------------------------------

func TestRun_NewDealer(t *testing.T) {
	srv := pappersServer(t, map[string]interface{}{
		"total": 1,
		"resultats": []map[string]interface{}{
			{
				"siren":          "123456789",
				"siret":          "12345678900012",
				"nom_entreprise": "GARAGE DUPONT SAS",
				"siege": map[string]interface{}{
					"adresse_ligne_1": "12 RUE DE LA PAIX",
					"code_postal":     "75001",
					"ville":           "PARIS",
				},
				"code_naf": "4511Z",
			},
		},
	})
	defer srv.Close()

	graph := newStub()
	p := pappers.NewWithClient(graph, "", srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := p.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.dealers) != 1 {
		t.Fatalf("want 1 dealer in KG, got %d", len(graph.dealers))
	}
	var d *kg.DealerEntity
	for _, v := range graph.dealers {
		d = v
	}
	if d.CanonicalName != "GARAGE DUPONT SAS" {
		t.Errorf("CanonicalName = %q, want GARAGE DUPONT SA", d.CanonicalName)
	}
	if d.CountryCode != "FR" {
		t.Errorf("CountryCode = %q, want FR", d.CountryCode)
	}
	if len(graph.locations) == 0 {
		t.Error("want location upserted")
	}
}

func TestRun_ExistingDealer_BumpsConfidence(t *testing.T) {
	srv := pappersServer(t, map[string]interface{}{
		"total": 1,
		"resultats": []map[string]interface{}{
			{
				"siret":          "12345678900012",
				"nom_entreprise": "DUPONT SAS",
				"siege":          map[string]interface{}{"ville": "PARIS", "code_postal": "75001"},
				"code_naf":       "4511Z",
			},
		},
	})
	defer srv.Close()

	graph := newStub()
	// Pre-populate: the dealer already exists via A.FR.1
	graph.identifiers["SIRET:12345678900012"] = "dealer-existing"

	p := pappers.NewWithClient(graph, "", srv.URL, &http.Client{Timeout: 5 * time.Second})
	_, err := p.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, bumped := graph.confidences["dealer-existing"]; !bumped {
		t.Error("want confidence bumped for existing dealer, got nothing")
	}
}

func TestRun_Checkpoint_Advances(t *testing.T) {
	srv := pappersServer(t, map[string]interface{}{
		"total":     0,
		"resultats": []map[string]interface{}{},
	})
	defer srv.Close()

	graph := newStub()
	graph.state["pappers:fr:next_dept_index"] = "5" // start at index 5

	p := pappers.NewWithClient(graph, "", srv.URL, &http.Client{Timeout: 5 * time.Second})
	_, err := p.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// After run, checkpoint should be 6
	if graph.state["pappers:fr:next_dept_index"] != "6" {
		t.Errorf("checkpoint = %q, want 6", graph.state["pappers:fr:next_dept_index"])
	}
}

func TestRun_HTTP429_ReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	graph := newStub()
	p := pappers.NewWithClient(graph, "", srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := p.Run(context.Background())
	if err == nil {
		t.Error("want error on 429, got nil")
	}
	if result.Errors == 0 {
		t.Error("want errors > 0 on 429")
	}
}
