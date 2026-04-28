package gewest_be_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_j/gewest_be"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	dealers    []*kg.DealerProvinceCandidate
	subRegions map[string]string
}

func (g *stubGraph) ListDealersByCountry(_ context.Context, _ string) ([]*kg.DealerProvinceCandidate, error) {
	return g.dealers, nil
}
func (g *stubGraph) UpdateDealerSubRegion(_ context.Context, id, region string) error {
	if g.subRegions == nil {
		g.subRegions = make(map[string]string)
	}
	g.subRegions[id] = region
	return nil
}

func TestGewestForPostalCode(t *testing.T) {
	cases := []struct {
		pc   string
		want gewest_be.GewestCode
	}{
		{"1000", gewest_be.GewestBrussels}, // Brussels
		{"1050", gewest_be.GewestBrussels}, // Ixelles
		{"1299", gewest_be.GewestBrussels},
		{"2000", gewest_be.GewestVlaams},   // Antwerp
		{"3000", gewest_be.GewestVlaams},   // Leuven
		{"8000", gewest_be.GewestVlaams},   // Bruges
		{"9000", gewest_be.GewestVlaams},   // Ghent
		{"4000", gewest_be.GewestWallonie}, // Liège
		{"5000", gewest_be.GewestWallonie}, // Namur
		{"7000", gewest_be.GewestWallonie}, // Mons
		{"",     ""},
		{"abc",  ""},
	}
	for _, tc := range cases {
		got := gewest_be.GewestForPostalCode(tc.pc)
		if got != tc.want {
			t.Errorf("GewestForPostalCode(%q) = %q, want %q", tc.pc, got, tc.want)
		}
	}
}

func TestRun_ClassifiesDealers(t *testing.T) {
	pc1 := "1050" // Brussels
	pc2 := "9000" // Ghent (Flemish)
	pc3 := "4000" // Liège (Walloon)

	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			{DealerID: "D1", PostalCode: &pc1, CountryCode: "BE"},
			{DealerID: "D2", PostalCode: &pc2, CountryCode: "BE"},
			{DealerID: "D3", PostalCode: &pc3, CountryCode: "BE"},
		},
	}
	c := gewest_be.New(graph)
	result, err := c.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 3 {
		t.Errorf("want 3 classified, got %d", result.Discovered)
	}
	if graph.subRegions["D1"] != string(gewest_be.GewestBrussels) {
		t.Errorf("D1 = %q, want BE-BRU", graph.subRegions["D1"])
	}
	if graph.subRegions["D2"] != string(gewest_be.GewestVlaams) {
		t.Errorf("D2 = %q, want BE-VLG", graph.subRegions["D2"])
	}
	if graph.subRegions["D3"] != string(gewest_be.GewestWallonie) {
		t.Errorf("D3 = %q, want BE-WAL", graph.subRegions["D3"])
	}
}
