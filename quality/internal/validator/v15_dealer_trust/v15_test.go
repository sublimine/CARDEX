package v15_dealer_trust_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v15_dealer_trust"
)

// mockTrustStore implements TrustStore for testing.
type mockTrustStore struct {
	dealer *v15_dealer_trust.DealerRecord
	err    error
}

func (m *mockTrustStore) GetDealerByID(_ context.Context, _ string) (*v15_dealer_trust.DealerRecord, error) {
	return m.dealer, m.err
}

func vehicle(dealerID string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", DealerID: dealerID}
}

func dealer(id string, score float64, sources int) *v15_dealer_trust.DealerRecord {
	return &v15_dealer_trust.DealerRecord{ID: id, Name: "Test Dealer", ConfidenceScore: score, DataSources: sources}
}

// TestV15_TrustedDealer verifies that a high-confidence dealer (>0.85) passes.
func TestV15_TrustedDealer(t *testing.T) {
	store := &mockTrustStore{dealer: dealer("D1", 0.92, 4)}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D1"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for trusted dealer, issue: %s", res.Issue)
	}
	if res.Evidence["confidence_score"] != "0.920" {
		t.Errorf("want confidence 0.920, got %q", res.Evidence["confidence_score"])
	}
}

// TestV15_ModerateDealer verifies that a mid-confidence dealer (0.70) is INFO pass.
func TestV15_ModerateDealer(t *testing.T) {
	store := &mockTrustStore{dealer: dealer("D2", 0.70, 2)}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D2"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for moderate dealer, issue: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for moderate dealer, got %s", res.Severity)
	}
}

// TestV15_LowConfidenceDealer verifies that a low-confidence dealer (0.45) is WARNING.
func TestV15_LowConfidenceDealer(t *testing.T) {
	store := &mockTrustStore{dealer: dealer("D3", 0.45, 1)}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D3"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for low-confidence dealer, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for low-confidence dealer, got %s", res.Severity)
	}
}

// TestV15_UnknownDealer verifies that a dealer absent from KG is CRITICAL.
func TestV15_UnknownDealer(t *testing.T) {
	store := &mockTrustStore{dealer: nil} // nil = not found
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("UNKNOWN_DEALER"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for unknown dealer, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for unknown dealer, got %s", res.Severity)
	}
}

// TestV15_VeryLowConfidence verifies that a near-zero confidence dealer is CRITICAL.
func TestV15_VeryLowConfidence(t *testing.T) {
	store := &mockTrustStore{dealer: dealer("D5", 0.12, 0)}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D5"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 0.12 confidence, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for <0.30 confidence, got %s", res.Severity)
	}
}

// TestV15_StoreError_SoftFail verifies that a store error is soft (INFO, not a pipeline failure).
func TestV15_StoreError_SoftFail(t *testing.T) {
	store := &mockTrustStore{err: errors.New("database locked")}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D6"))
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true (soft fail) when store returns error")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for store error, got %s", res.Severity)
	}
}

// ── Trust ramp-up tests ────────────────────────────────────────────────────────

func dealerWithAge(id string, score float64, sources int, createdAt time.Time) *v15_dealer_trust.DealerRecord {
	return &v15_dealer_trust.DealerRecord{
		ID: id, Name: "Test Dealer",
		ConfidenceScore: score, DataSources: sources,
		CreatedAt: createdAt,
	}
}

// TestV15_TrustRampUp_NewDealer verifies that a 5-day-old dealer has its
// confidence score capped at 0.5 even when the raw score is high (0.92).
func TestV15_TrustRampUp_NewDealer(t *testing.T) {
	d := dealerWithAge("D_NEW", 0.92, 4, time.Now().AddDate(0, 0, -5))
	store := &mockTrustStore{dealer: d}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D_NEW"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Confidence > 0.5 {
		t.Errorf("new dealer (5d): want confidence ≤ 0.5, got %.3f", res.Confidence)
	}
	if res.Evidence["trust_ramp_up"] != "true" {
		t.Errorf("new dealer (5d): want evidence trust_ramp_up=true, got %q", res.Evidence["trust_ramp_up"])
	}
}

// TestV15_TrustRampUp_EstablishedDealer verifies that a 60-day-old dealer
// is NOT subject to the trust ramp-up cap.
func TestV15_TrustRampUp_EstablishedDealer(t *testing.T) {
	d := dealerWithAge("D_OLD", 0.92, 4, time.Now().AddDate(0, 0, -60))
	store := &mockTrustStore{dealer: d}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D_OLD"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Confidence <= 0.5 {
		t.Errorf("established dealer (60d): want confidence > 0.5, got %.3f", res.Confidence)
	}
	if res.Evidence["trust_ramp_up"] != "" {
		t.Errorf("established dealer (60d): want no trust_ramp_up evidence, got %q", res.Evidence["trust_ramp_up"])
	}
}

// TestV15_TrustRampUp_BoundaryDealer verifies that a dealer exactly 30 days old
// is NOT capped (boundary is inclusive: ≥30 days = established).
func TestV15_TrustRampUp_BoundaryDealer(t *testing.T) {
	// Use exact duration arithmetic (30 * 24h) so agedays is precisely 30.0,
	// avoiding the DST ambiguity of AddDate which can produce ~29.96 days.
	createdAt := time.Now().Add(-30 * 24 * time.Hour)
	d := dealerWithAge("D_BOUNDARY", 0.92, 4, createdAt)
	store := &mockTrustStore{dealer: d}
	val := v15_dealer_trust.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("D_BOUNDARY"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Confidence <= 0.5 {
		t.Errorf("boundary dealer (30d): want confidence > 0.5, got %.3f", res.Confidence)
	}
	if res.Evidence["trust_ramp_up"] != "" {
		t.Errorf("boundary dealer (30d): want no trust_ramp_up evidence, got %q", res.Evidence["trust_ramp_up"])
	}
}
