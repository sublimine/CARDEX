package utac_fr_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_i/utac_fr"
	"cardex.eu/discovery/internal/kg"
)

// ── Minimal KG stub ───────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	upserted    []string
	identAdded  []string
	locations   int
	discoveries int
}

func (g *stubGraph) FindDealerByIdentifier(_ context.Context, _ kg.IdentifierType, _ string) (string, error) {
	return "", nil // always new
}
func (g *stubGraph) UpsertDealer(_ context.Context, d *kg.DealerEntity) error {
	g.upserted = append(g.upserted, d.CanonicalName)
	return nil
}
func (g *stubGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	g.identAdded = append(g.identAdded, id.IdentifierValue)
	return nil
}
func (g *stubGraph) AddLocation(_ context.Context, _ *kg.DealerLocation) error {
	g.locations++
	return nil
}
func (g *stubGraph) RecordDiscovery(_ context.Context, _ *kg.DiscoveryRecord) error {
	g.discoveries++
	return nil
}
func (g *stubGraph) UpsertWebPresence(_ context.Context, _ *kg.DealerWebPresence) error {
	return nil
}

// ── apiResponse builder ───────────────────────────────────────────────────────

func makeAPIResponse(records []map[string]string) map[string]any {
	results := make([]map[string]string, len(records))
	copy(results, records)
	return map[string]any{
		"total_count": len(records),
		"results":     results,
	}
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestRun_ParsesCTCentres(t *testing.T) {
	pages := []any{
		makeAPIResponse([]map[string]string{
			{
				"no_agrement": "03G0001",
				"nom_centre":  "SECURITEST AUTO CONTROLE",
				"adresse":     "6 RUE DE LA CHARME",
				"code_postal": "03200",
				"commune":     "VICHY",
				"departement": "03 - Allier",
				"region_administrative": "Auvergne-Rhône-Alpes",
			},
			{
				"no_agrement": "75A0042",
				"nom_centre":  "AUTOSUR PARIS 15",
				"adresse":     "15 RUE LECOURBE",
				"code_postal": "75015",
				"commune":     "PARIS",
				"departement": "75 - Paris",
				"region_administrative": "Île-de-France",
			},
		}),
		// empty second page terminates pagination
		makeAPIResponse(nil),
	}
	pageIdx := 0

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if pageIdx >= len(pages) {
			json.NewEncoder(w).Encode(makeAPIResponse(nil))
			return
		}
		json.NewEncoder(w).Encode(pages[pageIdx])
		pageIdx++
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := utac_fr.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("want 2 discovered, got %d", result.Discovered)
	}
	if len(graph.upserted) != 2 {
		t.Errorf("want 2 upserted, got %d", len(graph.upserted))
	}
	if len(graph.identAdded) != 2 {
		t.Errorf("want 2 identifiers added, got %d", len(graph.identAdded))
	}
	if graph.identAdded[0] != "03G0001" {
		t.Errorf("want identifier 03G0001, got %q", graph.identAdded[0])
	}
}

func TestRun_SkipsEmptyIDOrName(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(makeAPIResponse([]map[string]string{
			{"no_agrement": "", "nom_centre": "NO ID CENTRE"},  // no_agrement empty
			{"no_agrement": "OK001", "nom_centre": ""},          // nom_centre empty
			{"no_agrement": "OK001", "nom_centre": "VALID CTR"}, // valid
		}))
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := utac_fr.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
}

func TestRun_DedupWithinPage(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(makeAPIResponse([]map[string]string{
			{"no_agrement": "DUPE01", "nom_centre": "CENTRE A"},
			{"no_agrement": "DUPE01", "nom_centre": "CENTRE A DUP"},
		}))
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := utac_fr.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (dedup), got %d", result.Discovered)
	}
}

func TestRun_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := utac_fr.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors == 0 {
		t.Error("expected at least 1 error for HTTP 503, got 0")
	}
}

func TestRun_SubTechID(t *testing.T) {
	graph := &stubGraph{}
	exec := utac_fr.NewWithBaseURL(graph, "http://127.0.0.1:0", 0)
	if exec.ID() != "I.FR.2" {
		t.Errorf("want ID I.FR.2, got %q", exec.ID())
	}
}
