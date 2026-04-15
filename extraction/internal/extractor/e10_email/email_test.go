package e10_email_test

import (
	"context"
	"errors"
	"testing"

	"cardex.eu/extraction/internal/extractor/e10_email"
	"cardex.eu/extraction/internal/pipeline"
)

// mockEmailReader implements EmailInventoryReader for testing.
type mockEmailReader struct {
	vehicles []*pipeline.VehicleRaw
	err      error
}

func (m *mockEmailReader) ReadPendingVehicles(_ context.Context, _ string) ([]*pipeline.VehicleRaw, error) {
	return m.vehicles, m.err
}
func (m *mockEmailReader) MarkConsumed(_ context.Context, _ string) error { return nil }

// TestE10_Applicable_WithHint verifies that Applicable returns true when the
// dealer has the "email_inventory" extraction hint.
func TestE10_Applicable_WithHint(t *testing.T) {
	strategy := e10_email.New()
	dealer := pipeline.Dealer{
		ID:              "D1",
		ExtractionHints: []string{"email_inventory"},
	}
	if !strategy.Applicable(dealer) {
		t.Error("want Applicable=true for email_inventory hint, got false")
	}
}

// TestE10_Applicable_WithoutHint verifies that Applicable returns false for
// dealers without the email hint (E10 should not be attempted for them).
func TestE10_Applicable_WithoutHint(t *testing.T) {
	strategy := e10_email.New()
	dealer := pipeline.Dealer{
		ID:              "D2",
		ExtractionHints: []string{"schema_org_detected"},
	}
	if strategy.Applicable(dealer) {
		t.Error("want Applicable=false for non-email dealer, got true")
	}
}

// TestE10_PendingAttachment_ReturnsVehicles verifies that when the staging
// reader returns vehicles, E10 surfaces them in the result.
func TestE10_PendingAttachment_ReturnsVehicles(t *testing.T) {
	make_ := "Toyota"
	model := "Yaris"
	reader := &mockEmailReader{
		vehicles: []*pipeline.VehicleRaw{
			{Make: &make_, Model: &model},
		},
	}
	strategy := e10_email.NewWithReader(reader)
	dealer := pipeline.Dealer{
		ID:              "D3",
		ExtractionHints: []string{"email_inventory"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 1 {
		t.Errorf("want 1 vehicle from email attachment, got %d", len(result.Vehicles))
	}
	if result.Strategy != "E10" {
		t.Errorf("want strategy E10, got %q", result.Strategy)
	}
}

// TestE10_NoAttachment_RecordsError verifies that when no pending attachment
// exists, E10 records an informational NO_EMAIL_ATTACHMENT error.
func TestE10_NoAttachment_RecordsError(t *testing.T) {
	reader := &mockEmailReader{vehicles: nil}
	strategy := e10_email.NewWithReader(reader)
	dealer := pipeline.Dealer{
		ID:              "D4",
		ExtractionHints: []string{"email_inventory"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles when no attachment, got %d", len(result.Vehicles))
	}
	hasError := false
	for _, e := range result.Errors {
		if e.Code == "NO_EMAIL_ATTACHMENT" {
			hasError = true
		}
	}
	if !hasError {
		t.Error("want NO_EMAIL_ATTACHMENT error, got none")
	}
}

// TestE10_ReaderError_Graceful verifies that a staging reader error is
// recorded as an error without propagating as a top-level Go error.
func TestE10_ReaderError_Graceful(t *testing.T) {
	reader := &mockEmailReader{err: errors.New("db connection refused")}
	strategy := e10_email.NewWithReader(reader)
	dealer := pipeline.Dealer{
		ID:              "D5",
		ExtractionHints: []string{"email_inventory"},
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles on reader error, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for reader failure")
	}
}
