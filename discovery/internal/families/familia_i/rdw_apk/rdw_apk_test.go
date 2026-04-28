package rdw_apk_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_i/rdw_apk"
	"cardex.eu/discovery/internal/kg"
)

// ── Minimal KG stub ───────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	upserted   []string // dealer names
	identAdded []string // identifier values
	locations  int
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

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestRun_ParsesStations(t *testing.T) {
	// Two stations on first page, empty second page.
	pages := [][]map[string]string{
		{
			{"erkenningsnummer_keuringsinstantie": "APK001", "handelsnaam": "Garage Jansen APK", "postcode": "1234 AB", "plaatsnaam": "Amsterdam", "straat": "Teststraat", "huisnummer": "1"},
			{"erkenningsnummer_keuringsinstantie": "APK002", "handelsnaam": "Auto Keuring Rotterdam", "postcode": "3000 BC", "plaatsnaam": "Rotterdam", "straat": "Keurweg", "huisnummer": "5"},
		},
		{},
	}
	pageIdx := 0

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if pageIdx >= len(pages) {
			json.NewEncoder(w).Encode([]map[string]string{})
			return
		}
		json.NewEncoder(w).Encode(pages[pageIdx])
		pageIdx++
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := rdw_apk.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("want 2 discovered, got %d", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("want 0 errors, got %d", result.Errors)
	}

	if len(graph.upserted) != 2 {
		t.Fatalf("want 2 upserts, got %d", len(graph.upserted))
	}
	if graph.upserted[0] != "Garage Jansen APK" {
		t.Errorf("upserted[0] = %q, want Garage Jansen APK", graph.upserted[0])
	}

	if len(graph.identAdded) != 2 {
		t.Errorf("want 2 identifiers, got %d", len(graph.identAdded))
	}
	if graph.identAdded[0] != "APK001" {
		t.Errorf("identAdded[0] = %q, want APK001", graph.identAdded[0])
	}
}

func TestRun_SkipsEmptyName(t *testing.T) {
	pages := [][]map[string]string{
		{
			{"erkenningsnummer_keuringsinstantie": "APK001", "handelsnaam": ""},
			{"erkenningsnummer_keuringsinstantie": "APK002", "handelsnaam": "Valid Garage"},
		},
		{},
	}
	pageIdx := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if pageIdx >= len(pages) {
			json.NewEncoder(w).Encode([]map[string]string{})
			return
		}
		json.NewEncoder(w).Encode(pages[pageIdx])
		pageIdx++
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := rdw_apk.NewWithBaseURL(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (empty name skipped), got %d", result.Discovered)
	}
}

func TestRun_DeduplicatesIDs(t *testing.T) {
	// Same APK ID appears in two pages.
	page := []map[string]string{
		{"erkenningsnummer_keuringsinstantie": "APK001", "handelsnaam": "Dup Garage"},
		{"erkenningsnummer_keuringsinstantie": "APK001", "handelsnaam": "Dup Garage Again"},
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(page)
		page = []map[string]string{} // empty on second call
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := rdw_apk.NewWithBaseURL(graph, srv.URL, 0)

	result, _ := exec.Run(context.Background())
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (duplicate ID skipped), got %d", result.Discovered)
	}
}
