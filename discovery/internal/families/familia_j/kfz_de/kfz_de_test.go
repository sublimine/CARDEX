package kfz_de_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_j/kfz_de"
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

// ── BundeslandForPLZ unit tests ───────────────────────────────────────────────

func TestBundeslandForPLZ(t *testing.T) {
	cases := []struct {
		plz  string
		want string
	}{
		// Bayern
		{"80331", "DE-BY"}, // Munich centre
		{"90402", "DE-BY"}, // Nuremberg
		// Berlin
		{"10115", "DE-BE"}, // Mitte
		{"14193", "DE-BE"}, // Charlottenburg
		// Hamburg
		{"20095", "DE-HH"},
		// NRW
		{"40210", "DE-NW"}, // Düsseldorf
		{"50667", "DE-NW"}, // Cologne
		// Baden-Württemberg
		{"70173", "DE-BW"}, // Stuttgart
		{"79098", "DE-BW"}, // Freiburg
		// Hessen
		{"60311", "DE-HE"}, // Frankfurt
		// Niedersachsen
		{"30159", "DE-NI"}, // Hannover
		// Sachsen
		{"01067", "DE-SN"}, // Dresden
		{"04109", "DE-SN"}, // Leipzig
		// Thüringen
		{"07743", "DE-TH"}, // Jena
		{"99084", "DE-TH"}, // Erfurt
		// Saarland
		{"66111", "DE-SL"}, // Saarbrücken
		// Schleswig-Holstein
		{"24103", "DE-SH"}, // Kiel
		// Empty / invalid
		{"", ""},
		{"ABC", ""},
		{"123", ""}, // too short
	}

	for _, tc := range cases {
		got := kfz_de.BundeslandForPLZ(tc.plz)
		if got != tc.want {
			t.Errorf("BundeslandForPLZ(%q) = %q, want %q", tc.plz, got, tc.want)
		}
	}
}

func TestZulassungsstelleURL_KnownBundesland(t *testing.T) {
	url := kfz_de.ZulassungsstelleURL("DE-BY")
	if url == "" {
		t.Error("want non-empty URL for DE-BY")
	}
}

func TestZulassungsstelleURL_UnknownBundesland(t *testing.T) {
	url := kfz_de.ZulassungsstelleURL("DE-XX")
	if url != "" {
		t.Errorf("want empty URL for unknown DE-XX, got %q", url)
	}
}

// ── Run integration tests ─────────────────────────────────────────────────────

func TestRun_ClassifiesDealers(t *testing.T) {
	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			plzCandidate("d1", "80331"), // Munich → BY
			plzCandidate("d2", "10115"), // Berlin → BE
			plzCandidate("d3", "40210"), // Düsseldorf → NW
		},
	}

	exec := kfz_de.New(graph)
	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 3 {
		t.Errorf("want 3 classified, got %d", result.Discovered)
	}
	if graph.subRegions["d1"] != "DE-BY" {
		t.Errorf("d1: want DE-BY, got %q", graph.subRegions["d1"])
	}
	if graph.subRegions["d2"] != "DE-BE" {
		t.Errorf("d2: want DE-BE, got %q", graph.subRegions["d2"])
	}
	if graph.subRegions["d3"] != "DE-NW" {
		t.Errorf("d3: want DE-NW, got %q", graph.subRegions["d3"])
	}
}

func TestRun_SkipsMissingPLZ(t *testing.T) {
	noPLZ := ""
	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			{DealerID: "d1", PostalCode: nil},
			{DealerID: "d2", PostalCode: &noPLZ},
			plzCandidate("d3", "80331"), // valid
		},
	}

	exec := kfz_de.New(graph)
	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 classified, got %d", result.Discovered)
	}
}

func TestRun_SubTechID(t *testing.T) {
	exec := kfz_de.New(&stubGraph{})
	if exec.ID() != "J.DE.2" {
		t.Errorf("want ID J.DE.2, got %q", exec.ID())
	}
}
