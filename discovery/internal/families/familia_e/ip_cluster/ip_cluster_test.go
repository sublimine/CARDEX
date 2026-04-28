package ip_cluster_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_e/ip_cluster"
	"cardex.eu/discovery/internal/kg"
)

// stubGraph stubs KG for E.3 tests.
type stubGraph struct {
	kg.KnowledgeGraph
	presences []*kg.DealerWebPresence
	clusters  []*kg.HostIPCluster
	dmsSet    map[string]string
}

func (g *stubGraph) ListWebPresencesForInfraScan(_ context.Context, _ string, _ int) ([]*kg.DealerWebPresence, error) {
	return g.presences, nil
}

func (g *stubGraph) ListHostIPClusters(_ context.Context, _ int) ([]*kg.HostIPCluster, error) {
	return g.clusters, nil
}

func (g *stubGraph) SetDMSProvider(_ context.Context, domain, provider string) error {
	if g.dmsSet == nil {
		g.dmsSet = map[string]string{}
	}
	g.dmsSet[domain] = provider
	return nil
}

func ptr(s string) *string { return &s }

// TestPropagatesWithinCluster: 3 dealers share an IP, one has dms_provider set.
// The other two should receive the provider.
func TestPropagatesWithinCluster(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{DealerID: "D1", Domain: "d1.example.de", DMSProvider: ptr("modix.de")},
			{DealerID: "D2", Domain: "d2.example.de"},
			{DealerID: "D3", Domain: "d3.example.de"},
		},
		clusters: []*kg.HostIPCluster{
			{HostIP: "1.2.3.4", DealerIDs: []string{"D1", "D2", "D3"}, Source: "CENSYS_HOST_ID"},
		},
	}
	c := ip_cluster.New(graph)
	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 2 {
		t.Errorf("want 2 propagated, got %d", result.Discovered)
	}
	if graph.dmsSet["d2.example.de"] != "modix.de" {
		t.Errorf("want d2 dms_provider=modix.de, got %q", graph.dmsSet["d2.example.de"])
	}
	if graph.dmsSet["d3.example.de"] != "modix.de" {
		t.Errorf("want d3 dms_provider=modix.de, got %q", graph.dmsSet["d3.example.de"])
	}
}

// TestNoProviderInCluster: cluster with no dms_provider set — nothing propagated.
func TestNoProviderInCluster(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{DealerID: "D1", Domain: "d1.example.de"},
			{DealerID: "D2", Domain: "d2.example.de"},
			{DealerID: "D3", Domain: "d3.example.de"},
		},
		clusters: []*kg.HostIPCluster{
			{HostIP: "1.2.3.4", DealerIDs: []string{"D1", "D2", "D3"}, Source: "SHODAN_HOST_ID"},
		},
	}
	c := ip_cluster.New(graph)
	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 propagated (no known provider), got %d", result.Discovered)
	}
	if len(graph.dmsSet) != 0 {
		t.Errorf("want 0 SetDMSProvider calls, got %d", len(graph.dmsSet))
	}
}

// TestAllAlreadySet: cluster where all presences already have dms_provider — no changes.
func TestAllAlreadySet(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{DealerID: "D1", Domain: "d1.example.de", DMSProvider: ptr("cdksite.com")},
			{DealerID: "D2", Domain: "d2.example.de", DMSProvider: ptr("cdksite.com")},
			{DealerID: "D3", Domain: "d3.example.de", DMSProvider: ptr("cdksite.com")},
		},
		clusters: []*kg.HostIPCluster{
			{HostIP: "5.6.7.8", DealerIDs: []string{"D1", "D2", "D3"}, Source: "CENSYS_HOST_ID"},
		},
	}
	c := ip_cluster.New(graph)
	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 (all already set), got %d", result.Discovered)
	}
	if len(graph.dmsSet) != 0 {
		t.Errorf("want 0 SetDMSProvider calls, got %d", len(graph.dmsSet))
	}
}

// TestCrossCountryCluster: cluster members from other countries not in the presences
// slice (filtered by country) are ignored.
func TestCrossCountryCluster(t *testing.T) {
	// Only D1 is in DE (current country). D2 and D3 are in FR — not in our presences.
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{DealerID: "D1", Domain: "d1.example.de", DMSProvider: ptr("incadea.com")},
		},
		clusters: []*kg.HostIPCluster{
			{HostIP: "9.0.0.1", DealerIDs: []string{"D1", "D2", "D3"}, Source: "CENSYS_HOST_ID"},
		},
	}
	c := ip_cluster.New(graph)
	result, err := c.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Only 1 country member and it already has provider — nothing to propagate.
	if result.Discovered != 0 {
		t.Errorf("want 0 (only 1 country member, already set), got %d", result.Discovered)
	}
}
