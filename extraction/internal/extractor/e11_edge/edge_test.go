package e11_edge_test

import (
	"context"
	"testing"

	"cardex.eu/extraction/internal/extractor/e11_edge"
	"cardex.eu/extraction/internal/pipeline"
)

// mockEdgeStore implements EdgeInventoryStore for testing.
type mockEdgeStore struct {
	vehicles []*pipeline.VehicleRaw
	consumed bool
}

func (m *mockEdgeStore) ReadPendingPush(_ context.Context, _ string) ([]*pipeline.VehicleRaw, error) {
	return m.vehicles, nil
}
func (m *mockEdgeStore) MarkConsumed(_ context.Context, _ string) error {
	m.consumed = true
	return nil
}

// TestE11_Priority verifies E11 has the highest priority (1500).
func TestE11_Priority(t *testing.T) {
	strategy := e11_edge.New()
	if got := strategy.Priority(); got != 1500 {
		t.Errorf("want Priority=1500 (highest), got %d", got)
	}
}

// TestE11_Applicable_EdgeHint verifies that Applicable returns true only for
// dealers with the "edge_client_registered" extraction hint.
func TestE11_Applicable_EdgeHint(t *testing.T) {
	strategy := e11_edge.New()

	withHint := pipeline.Dealer{ID: "D1", ExtractionHints: []string{"edge_client_registered"}}
	if !strategy.Applicable(withHint) {
		t.Error("want Applicable=true for edge_client_registered hint, got false")
	}

	withoutHint := pipeline.Dealer{ID: "D2", ExtractionHints: []string{"schema_org_detected"}}
	if strategy.Applicable(withoutHint) {
		t.Error("want Applicable=false for non-edge dealer, got true")
	}
}

// TestE11_PendingPush_ReturnsVehicles verifies that vehicles from a pending
// edge push are returned and the push is marked consumed.
func TestE11_PendingPush_ReturnsVehicles(t *testing.T) {
	make_ := "BMW"
	model := "320d"
	yr := 2022
	store := &mockEdgeStore{
		vehicles: []*pipeline.VehicleRaw{
			{Make: &make_, Model: &model, Year: &yr},
			{Make: &make_, Model: &model, Year: &yr},
		},
	}
	strategy := e11_edge.NewWithStore(store)
	dealer := pipeline.Dealer{
		ID:              "D3",
		ExtractionHints: []string{"edge_client_registered"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 2 {
		t.Errorf("want 2 vehicles from edge push, got %d", len(result.Vehicles))
	}
	if !store.consumed {
		t.Error("want push marked consumed after extraction, got false")
	}
	if result.Strategy != "E11" {
		t.Errorf("want strategy E11, got %q", result.Strategy)
	}
}

// TestE11_NoPendingPush verifies that when there is no pending push,
// E11 returns an empty result without errors.
func TestE11_NoPendingPush(t *testing.T) {
	store := &mockEdgeStore{vehicles: nil}
	strategy := e11_edge.NewWithStore(store)
	dealer := pipeline.Dealer{
		ID:              "D4",
		ExtractionHints: []string{"edge_client_registered"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles when no push pending, got %d", len(result.Vehicles))
	}
	if len(result.Errors) != 0 {
		t.Errorf("want 0 errors for empty push, got %v", result.Errors)
	}
}
