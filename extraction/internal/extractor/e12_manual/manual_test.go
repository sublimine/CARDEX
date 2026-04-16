package e12_manual_test

import (
	"context"
	"testing"

	"cardex.eu/extraction/internal/extractor/e12_manual"
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

// TestE12_Applicable_Always verifies that E12 returns true for all dealers
// (it is the universal fallback).
func TestE12_Applicable_Always(t *testing.T) {
	strategy := e12_manual.New()
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

// TestE12_Priority verifies E12 has the correct cascade priority (0 = last resort).
func TestE12_Priority(t *testing.T) {
	strategy := e12_manual.New()
	if got := strategy.Priority(); got != 0 {
		t.Errorf("want Priority=0 (last resort), got %d", got)
	}
}

// TestE12_EnqueuesDealer verifies that Extract calls the queue writer with
// the correct dealer ID.
func TestE12_EnqueuesDealer(t *testing.T) {
	q := &mockQueue{}
	strategy := e12_manual.NewWithQueue(q)
	dealer := pipeline.Dealer{ID: "DEALER_42", Domain: "dealer.example.de"}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(q.enqueued) != 1 || q.enqueued[0] != "DEALER_42" {
		t.Errorf("want DEALER_42 enqueued, got %v", q.enqueued)
	}
	// E12 returns 0 vehicles (humans haven't reviewed yet).
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from E12, got %d", len(result.Vehicles))
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
	if result.Strategy != "E12" {
		t.Errorf("want strategy E12, got %q", result.Strategy)
	}
}
