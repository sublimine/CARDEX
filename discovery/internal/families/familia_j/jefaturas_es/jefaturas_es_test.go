package jefaturas_es_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_j/jefaturas_es"
	"cardex.eu/discovery/internal/kg"
)

// ── Minimal KG stub ───────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	dealers    []*kg.DealerProvinceCandidate
	subRegions map[string]string
}

func (g *stubGraph) ListDealersByCountry(_ context.Context, _ string) ([]*kg.DealerProvinceCandidate, error) {
	return g.dealers, nil
}
func (g *stubGraph) UpdateDealerSubRegion(_ context.Context, dealerID, subRegion string) error {
	if g.subRegions == nil {
		g.subRegions = make(map[string]string)
	}
	g.subRegions[dealerID] = subRegion
	return nil
}

func plzCandidate(id, plz string) *kg.DealerProvinceCandidate {
	return &kg.DealerProvinceCandidate{DealerID: id, PostalCode: &plz}
}

// ── ProvinceForPLZ unit tests ─────────────────────────────────────────────────

func TestProvinceForPLZ(t *testing.T) {
	cases := []struct {
		plz         string
		wantISO     string
		wantFound   bool
	}{
		{"28001", "ES-M", true},   // Madrid
		{"08001", "ES-B", true},   // Barcelona
		{"46001", "ES-V", true},   // Valencia
		{"41001", "ES-SE", true},  // Sevilla
		{"07001", "ES-PM", true},  // Illes Balears
		{"35001", "ES-GC", true},  // Las Palmas
		{"51001", "ES-CE", true},  // Ceuta
		{"52001", "ES-ML", true},  // Melilla
		{"00000", "", false},       // invalid province 00
		{"99999", "", false},       // out of range
		{"", "", false},
		{"abc12", "", false},
	}

	for _, tc := range cases {
		prov, ok := jefaturas_es.ProvinceForPLZ(tc.plz)
		if ok != tc.wantFound {
			t.Errorf("ProvinceForPLZ(%q): ok=%v want %v", tc.plz, ok, tc.wantFound)
			continue
		}
		if ok && prov.ISOCode != tc.wantISO {
			t.Errorf("ProvinceForPLZ(%q): ISO=%q want %q", tc.plz, prov.ISOCode, tc.wantISO)
		}
	}
}

func TestJefaturaURL_Madrid(t *testing.T) {
	url := jefaturas_es.JefaturaURL("28")
	if url == "" {
		t.Error("want non-empty URL for province 28 (Madrid)")
	}
}

func TestJefaturaURL_NotFound(t *testing.T) {
	url := jefaturas_es.JefaturaURL("99")
	if url != "" {
		t.Errorf("want empty URL for invalid province 99, got %q", url)
	}
}

func TestCount(t *testing.T) {
	if jefaturas_es.Count() != 52 {
		t.Errorf("want Count() == 52, got %d", jefaturas_es.Count())
	}
}

// ── Run integration tests ─────────────────────────────────────────────────────

func TestRun_ClassifiesDealers(t *testing.T) {
	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			plzCandidate("d1", "28001"), // Madrid → ES-M
			plzCandidate("d2", "08001"), // Barcelona → ES-B
			plzCandidate("d3", "41001"), // Sevilla → ES-SE
		},
	}

	exec := jefaturas_es.New(graph)
	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 3 {
		t.Errorf("want 3 classified, got %d", result.Discovered)
	}
	if graph.subRegions["d1"] != "ES-M" {
		t.Errorf("d1: want ES-M, got %q", graph.subRegions["d1"])
	}
	if graph.subRegions["d2"] != "ES-B" {
		t.Errorf("d2: want ES-B, got %q", graph.subRegions["d2"])
	}
}

func TestRun_SkipsMissingPLZ(t *testing.T) {
	noPLZ := ""
	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			{DealerID: "d1", PostalCode: nil},
			{DealerID: "d2", PostalCode: &noPLZ},
			plzCandidate("d3", "28001"),
		},
	}

	exec := jefaturas_es.New(graph)
	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 classified, got %d", result.Discovered)
	}
}

func TestRun_SubTechID(t *testing.T) {
	exec := jefaturas_es.New(&stubGraph{})
	if exec.ID() != "J.ES.2" {
		t.Errorf("want ID J.ES.2, got %q", exec.ID())
	}
}
