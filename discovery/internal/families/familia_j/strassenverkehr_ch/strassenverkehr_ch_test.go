package strassenverkehr_ch_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_j/strassenverkehr_ch"
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

// ── CantonForPLZ unit tests ───────────────────────────────────────────────────

func TestCantonForPLZ(t *testing.T) {
	cases := []struct {
		plz       string
		wantCanton string
		wantOK    bool
	}{
		{"8001", "CH-ZH", true},   // Zurich city
		{"3011", "CH-BE", true},   // Bern city
		{"4051", "CH-BS", true},   // Basel-Stadt
		{"1003", "CH-VD", true},   // Lausanne (Vaud)
		{"1200", "CH-GE", true},   // Geneva
		{"6300", "CH-ZG", true},   // Zug
		{"7000", "CH-GR", true},   // Chur (Graubünden)
		{"6600", "CH-TI", true},   // Ticino
		{"9000", "CH-SG", true},   // St. Gallen
		{"6000", "CH-LU", true},   // Lucerne
		{"", "", false},
		{"abc", "", false},
		{"9999", "", false},        // no matching range
	}

	for _, tc := range cases {
		canton, ok := strassenverkehr_ch.CantonForPLZ(tc.plz)
		if ok != tc.wantOK {
			t.Errorf("CantonForPLZ(%q): ok=%v want %v", tc.plz, ok, tc.wantOK)
			continue
		}
		if ok && canton != tc.wantCanton {
			t.Errorf("CantonForPLZ(%q): canton=%q want %q", tc.plz, canton, tc.wantCanton)
		}
	}
}

func TestSVAWebsiteURL_KnownCanton(t *testing.T) {
	url := strassenverkehr_ch.SVAWebsiteURL("CH-ZH")
	if url == "" {
		t.Error("want non-empty URL for CH-ZH")
	}
}

func TestSVAWebsiteURL_UnknownCanton(t *testing.T) {
	url := strassenverkehr_ch.SVAWebsiteURL("CH-XX")
	if url != "" {
		t.Errorf("want empty URL for unknown CH-XX, got %q", url)
	}
}

// ── Run integration tests ─────────────────────────────────────────────────────

func TestRun_ClassifiesDealers(t *testing.T) {
	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			plzCandidate("d1", "8001"), // Zurich → CH-ZH
			plzCandidate("d2", "3011"), // Bern → CH-BE
			plzCandidate("d3", "1200"), // Geneva → CH-GE
		},
	}

	exec := strassenverkehr_ch.New(graph)
	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 3 {
		t.Errorf("want 3 classified, got %d", result.Discovered)
	}
	if graph.subRegions["d1"] != "CH-ZH" {
		t.Errorf("d1: want CH-ZH, got %q", graph.subRegions["d1"])
	}
}

func TestRun_SubTechID(t *testing.T) {
	exec := strassenverkehr_ch.New(&stubGraph{})
	if exec.ID() != "J.CH.2" {
		t.Errorf("want ID J.CH.2, got %q", exec.ID())
	}
}
