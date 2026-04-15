package province_nl_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_j/province_nl"
	"cardex.eu/discovery/internal/kg"
)

// -- KG stub ------------------------------------------------------------------

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

// -- PostalCode lookup tests --------------------------------------------------

func TestProvinceForPostalCode(t *testing.T) {
	cases := []struct {
		pc   string
		want string
	}{
		{"1017", "NL-NH"}, // Amsterdam
		{"3012", "NL-ZH"}, // Rotterdam
		{"3511", "NL-UT"}, // Utrecht
		{"5600", "NL-NB"}, // Eindhoven
		{"9700", "NL-GR"}, // Groningen
		{"8900", "NL-FR"}, // Leeuwarden
		{"9900", "NL-GR"},
		{"1300", "NL-FL"}, // Almere
		{"6200", "NL-LI"}, // Maastricht
		{"9999", "NL-GR"},
		{"",     ""},      // empty
		{"abc",  ""},      // non-numeric
	}
	for _, tc := range cases {
		got := province_nl.ProvinceForPostalCode(tc.pc)
		if got != tc.want {
			t.Errorf("ProvinceForPostalCode(%q) = %q, want %q", tc.pc, got, tc.want)
		}
	}
}

// -- Classifier run tests -----------------------------------------------------

func TestRun_ClassifiesDealers(t *testing.T) {
	pc1 := "1017"
	pc2 := "5600"
	pc3 := "" // no postal code, should be skipped

	graph := &stubGraph{
		dealers: []*kg.DealerProvinceCandidate{
			{DealerID: "D1", PostalCode: &pc1, CountryCode: "NL"},
			{DealerID: "D2", PostalCode: &pc2, CountryCode: "NL"},
			{DealerID: "D3", PostalCode: &pc3, CountryCode: "NL"},
		},
	}
	c := province_nl.New(graph)
	result, err := c.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("want 2 classified, got %d", result.Discovered)
	}
	if graph.subRegions["D1"] != "NL-NH" {
		t.Errorf("D1 province = %q, want NL-NH", graph.subRegions["D1"])
	}
	if graph.subRegions["D2"] != "NL-NB" {
		t.Errorf("D2 province = %q, want NL-NB", graph.subRegions["D2"])
	}
	if _, set := graph.subRegions["D3"]; set {
		t.Error("D3 (no postal code) should not be classified")
	}
}
