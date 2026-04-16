package e11_manual_test

import (
	"context"
	"testing"

	"cardex.eu/extraction/internal/extractor/e11_manual"
	"cardex.eu/extraction/internal/pipeline"
)

// mockQueue implements ManualQueueWriter for testing.
type mockQueue struct {
	enqueued []string
}

func (m *mockQueue) EnqueueDealer(_ context.Context, dealerID string) error {
	m.enqueued = append(m.enqueued, dealerID)
	return nil
}

// TestE11_Applicable_Always verifies that E11 returns true for all dealers
// (it is the universal fallback).
func TestE11_Applicable_Always(t *testing.T) {
	strategy := e11_manual.New()
	for _, dealer := range []pipeline.Dealer{
		{ID: "D1"},
		{ID: "D2", PlatformType: "CMS_WORDPRESS"},
		{ID: "D3", DMSProvider: "incadea"},
	} {
		if !strategy.Applicable(dealer) {
			t.Errorf("want Applicable=true for dealer %s, got false", dealer.ID)
		}
	}
}

// TestE11_Priority verifies E11 has the correct cascade priority (100 = lowest).
func TestE11_Priority(t *testing.T) {
	strategy := e11_manual.New()
	if got := strategy.Priority(); got != 100 {
		t.Errorf("want Priority=100, got %d", got)
	}
}

// TestE11_EnqueuesDealer verifies that Extract calls the queue writer with
// the correct dealer ID.
func TestE11_EnqueuesDealer(t *testing.T) {
	q := &mockQueue{}
	strategy := e11_manual.NewWithQueue(q)
	dealer := pipeline.Dealer{ID: "DEALER_42", Domain: "dealer.example.de"}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(q.enqueued) != 1 || q.enqueued[0] != "DEALER_42" {
		t.Errorf("want DEALER_42 enqueued, got %v", q.enqueued)
	}
	// E11 returns 0 vehicles (humans haven't reviewed yet).
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from E11, got %d", len(result.Vehicles))
	}
	hasError := false
	for _, e := range result.Errors {
		if e.Code == "MANUAL_REVIEW_REQUIRED" {
			hasError = true
		}
	}
	if !hasError {
		t.Error("want MANUAL_REVIEW_REQUIRED error code, got none")
	}
	if result.Strategy != "E11" {
		t.Errorf("want strategy E11, got %q", result.Strategy)
	}
}
