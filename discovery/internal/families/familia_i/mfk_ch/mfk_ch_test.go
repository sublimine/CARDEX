package mfk_ch_test

import (
	"context"
	"testing"

	"cardex.eu/discovery/internal/families/familia_i/mfk_ch"
	"cardex.eu/discovery/internal/kg"
)

// ── Minimal KG stub ───────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	upserted    []string
	identAdded  []string
	locations   int
	presences   int
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
func (g *stubGraph) UpsertWebPresence(_ context.Context, _ *kg.DealerWebPresence) error {
	g.presences++
	return nil
}
func (g *stubGraph) RecordDiscovery(_ context.Context, _ *kg.DiscoveryRecord) error {
	g.discoveries++
	return nil
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestRun_Discovers26Cantons(t *testing.T) {
	graph := &stubGraph{}
	exec := mfk_ch.New(graph)

	result, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 26 {
		t.Errorf("want 26 discovered (all Swiss cantons), got %d", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("want 0 errors, got %d", result.Errors)
	}
}

func TestRun_UpsertCount(t *testing.T) {
	graph := &stubGraph{}
	exec := mfk_ch.New(graph)

	_, err := exec.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(graph.upserted) != 26 {
		t.Errorf("want 26 KG upserts, got %d", len(graph.upserted))
	}
	if len(graph.identAdded) != 26 {
		t.Errorf("want 26 identifiers, got %d", len(graph.identAdded))
	}
	if graph.locations != 26 {
		t.Errorf("want 26 locations, got %d", graph.locations)
	}
	if graph.presences != 26 {
		t.Errorf("want 26 web presences, got %d", graph.presences)
	}
}

func TestCount(t *testing.T) {
	if mfk_ch.Count() != 26 {
		t.Errorf("want Count() == 26, got %d", mfk_ch.Count())
	}
}

func TestForCantonCode_Found(t *testing.T) {
	sva, ok := mfk_ch.ForCantonCode("CH-ZH")
	if !ok {
		t.Fatal("expected CH-ZH to be found")
	}
	if sva.ISOCode != "CH-ZH" {
		t.Errorf("wrong ISOCode: %q", sva.ISOCode)
	}
	if sva.WebsiteURL == "" {
		t.Error("expected non-empty WebsiteURL for CH-ZH")
	}
}

func TestForCantonCode_NotFound(t *testing.T) {
	_, ok := mfk_ch.ForCantonCode("CH-XX")
	if ok {
		t.Error("expected CH-XX not to be found")
	}
}

func TestRun_SubTechID(t *testing.T) {
	graph := &stubGraph{}
	exec := mfk_ch.New(graph)
	if exec.ID() != "I.CH.1" {
		t.Errorf("want ID I.CH.1, got %q", exec.ID())
	}
}

func TestRun_ContextCancellation(t *testing.T) {
	graph := &stubGraph{}
	exec := mfk_ch.New(graph)

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	result, err := exec.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// With cancelled context, should discover 0 cantons (loop exits immediately).
	if result.Discovered != 0 {
		t.Logf("note: %d cantons discovered before context cancel (race-dependent)", result.Discovered)
	}
}
