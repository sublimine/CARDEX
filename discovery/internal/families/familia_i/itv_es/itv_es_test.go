package itv_es_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_i/itv_es"
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
	return "", nil
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

// ── ArcGIS response builders ──────────────────────────────────────────────────

func arcPage(stations []map[string]any, exceeded bool) map[string]any {
	features := make([]map[string]any, len(stations))
	for i, s := range stations {
		features[i] = map[string]any{"attributes": s}
	}
	return map[string]any{
		"features":              features,
		"exceededTransferLimit": exceeded,
	}
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestRun_BlockedWhenNoURL(t *testing.T) {
	graph := &stubGraph{}
	// New() uses DefaultArcGISServiceURL which is ""
	exec := itv_es.New(graph)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered when URL is empty, got %d", result.Discovered)
	}
}

func TestRun_ParsesArcGISStations(t *testing.T) {
	pages := []map[string]any{
		arcPage([]map[string]any{
			{"OBJECTID": float64(1), "NOMBRE": "ITV MADRID NORTE", "MUNICIPIO": "MADRID", "CP": "28001"},
			{"OBJECTID": float64(2), "NOMBRE": "ITV BARCELONA SUD", "MUNICIPIO": "BARCELONA", "CP": "08001"},
		}, true), // exceeded → more pages
		arcPage([]map[string]any{
			{"OBJECTID": float64(3), "NOMBRE": "ITV VALENCIA", "MUNICIPIO": "VALENCIA", "CP": "46001"},
		}, false), // not exceeded → last page
	}
	pageIdx := 0

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if pageIdx >= len(pages) {
			json.NewEncoder(w).Encode(arcPage(nil, false))
			return
		}
		json.NewEncoder(w).Encode(pages[pageIdx])
		pageIdx++
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := itv_es.NewWithConfig(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 3 {
		t.Errorf("want 3 discovered, got %d", result.Discovered)
	}
}

func TestRun_SkipsMissingNameOrID(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(arcPage([]map[string]any{
			{"NOMBRE": "NO ID STATION"},                               // no OBJECTID
			{"OBJECTID": float64(10), "NOMBRE": ""},                   // empty name
			{"OBJECTID": float64(11), "NOMBRE": "VALID ITV STATION"}, // valid
		}, false))
	}))
	defer srv.Close()

	graph := &stubGraph{}
	exec := itv_es.NewWithConfig(graph, srv.URL, 0)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
}

func TestRun_SubTechID(t *testing.T) {
	graph := &stubGraph{}
	exec := itv_es.New(graph)
	if exec.ID() != "I.ES.1" {
		t.Errorf("want ID I.ES.1, got %q", exec.ID())
	}
}
