package subdomain_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_n/subdomain"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	presences  []*kg.DealerWebPresence
	presences2 map[string]string // domain -> dealerID (existing)
	upserted   []*kg.DealerWebPresence
	identifiers []*kg.DealerIdentifier
}

func (g *stubGraph) ListWebPresencesForInfraScan(_ context.Context, _ string, _ int) ([]*kg.DealerWebPresence, error) {
	return g.presences, nil
}
func (g *stubGraph) FindDealerIDByDomain(_ context.Context, domain string) (string, error) {
	if g.presences2 != nil {
		return g.presences2[domain], nil
	}
	return "", nil
}
func (g *stubGraph) UpsertWebPresence(_ context.Context, wp *kg.DealerWebPresence) error {
	g.upserted = append(g.upserted, wp)
	return nil
}
func (g *stubGraph) AddIdentifier(_ context.Context, id *kg.DealerIdentifier) error {
	g.identifiers = append(g.identifiers, id)
	return nil
}

func TestRun_NoPresences_ReturnsEmpty(t *testing.T) {
	graph := &stubGraph{}
	// lookup always returns NXDOMAIN
	e := subdomain.NewWithLookup(graph, func(_ context.Context, _ string) ([]string, error) {
		return nil, nil
	})
	result, err := e.Run(context.Background(), "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
}

func TestRun_SubdomainResolves_UpsertedAsPresence(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "www.autohaus-test.de"},
		},
	}

	// Only "gebraucht.autohaus-test.de" resolves.
	lookup := func(_ context.Context, host string) ([]string, error) {
		if host == "gebraucht.autohaus-test.de" {
			return []string{"1.2.3.4"}, nil
		}
		return nil, nil
	}
	e := subdomain.NewWithLookup(graph, lookup)

	result, err := e.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.upserted) != 1 {
		t.Fatalf("want 1 upserted presence, got %d", len(graph.upserted))
	}
	if graph.upserted[0].Domain != "gebraucht.autohaus-test.de" {
		t.Errorf("unexpected domain: %s", graph.upserted[0].Domain)
	}
	if graph.upserted[0].DealerID != "D1" {
		t.Errorf("want dealer D1, got %s", graph.upserted[0].DealerID)
	}
}

func TestRun_SkipsAlreadyKnownSubdomain(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "autohaus-test.de"},
		},
		presences2: map[string]string{
			"gebraucht.autohaus-test.de": "D1", // already in KG
		},
	}
	lookup := func(_ context.Context, host string) ([]string, error) {
		if host == "gebraucht.autohaus-test.de" {
			return []string{"1.2.3.4"}, nil
		}
		return nil, nil
	}
	e := subdomain.NewWithLookup(graph, lookup)

	result, err := e.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 (already known), got %d", result.Discovered)
	}
}

func TestRun_StripWWW_FromBaseDomain(t *testing.T) {
	// Domain starts with www. -- N.3 should probe "www.www.autohaus-test.de" -> NXDOMAIN
	// but "www.autohaus-test.de" should be skipped (already known via presence).
	// And "gebraucht.autohaus-test.de" should resolve.
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{WebID: "W1", DealerID: "D1", Domain: "www.autohaus-test.de"},
		},
	}
	resolved := []string{}
	lookup := func(_ context.Context, host string) ([]string, error) {
		if host == "gebraucht.autohaus-test.de" {
			resolved = append(resolved, host)
			return []string{"9.9.9.9"}, nil
		}
		return nil, nil
	}
	e := subdomain.NewWithLookup(graph, lookup)
	result, err := e.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (www. stripped), got %d", result.Discovered)
	}
}
