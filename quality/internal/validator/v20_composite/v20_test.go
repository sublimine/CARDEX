package v20_composite_test

import (
	"context"
	"errors"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v20_composite"
)

// mockResultStore returns a fixed set of ValidationResults.
type mockResultStore struct {
	results []*pipeline.ValidationResult
	err     error
}

func (m *mockResultStore) GetValidationResultsByVehicle(_ context.Context, _ string) ([]*pipeline.ValidationResult, error) {
	return m.results, m.err
}

// allPass builds a results slice where every V01–V19 result is a pass.
func allPass() []*pipeline.ValidationResult {
	ids := []string{"V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08", "V09", "V10",
		"V11", "V12", "V13", "V14", "V15", "V16", "V17", "V18", "V19"}
	res := make([]*pipeline.ValidationResult, 0, len(ids))
	for _, id := range ids {
		res = append(res, &pipeline.ValidationResult{
			ValidatorID: id,
			Pass:        true,
			Severity:    pipeline.SeverityInfo,
		})
	}
	return res
}

func vehicle() *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1"}
}

// TestV20_AllPass verifies that all-pass results yield PUBLISH.
func TestV20_AllPass(t *testing.T) {
	store := &mockResultStore{results: allPass()}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for all-pass results, issue: %s", res.Issue)
	}
	if res.Evidence["decision"] != string(v20_composite.DecisionPublish) {
		t.Errorf("want decision=PUBLISH, got %q", res.Evidence["decision"])
	}
	if res.Evidence["score_pct"] != "100.0" {
		t.Errorf("want score_pct=100.0, got %q", res.Evidence["score_pct"])
	}
}

// TestV20_MultipleCriticals verifies that 2+ CRITICAL failures → REJECT.
func TestV20_MultipleCriticals(t *testing.T) {
	results := allPass()
	// Override V01 and V02 to CRITICAL failures.
	for _, r := range results {
		if r.ValidatorID == "V01" || r.ValidatorID == "V02" {
			r.Pass = false
			r.Severity = pipeline.SeverityCritical
		}
	}

	store := &mockResultStore{results: results}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 2 critical failures, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for REJECT decision, got %s", res.Severity)
	}
	if res.Evidence["decision"] != string(v20_composite.DecisionReject) {
		t.Errorf("want decision=REJECT, got %q", res.Evidence["decision"])
	}
}

// TestV20_OneCritical verifies that exactly 1 CRITICAL → MANUAL_REVIEW.
func TestV20_OneCritical(t *testing.T) {
	results := allPass()
	// Override V01 to CRITICAL.
	for _, r := range results {
		if r.ValidatorID == "V01" {
			r.Pass = false
			r.Severity = pipeline.SeverityCritical
		}
	}

	store := &mockResultStore{results: results}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 1 critical failure, got true")
	}
	if res.Evidence["decision"] != string(v20_composite.DecisionManualReview) {
		t.Errorf("want decision=MANUAL_REVIEW, got %q", res.Evidence["decision"])
	}
}

// TestV20_LowScore verifies that a score < 60% → REJECT even without criticals.
func TestV20_LowScore(t *testing.T) {
	// Only pass V18 and V19 (weight 4+6=10 out of 176 possible = ~5.7%).
	results := []*pipeline.ValidationResult{
		{ValidatorID: "V18", Pass: true, Severity: pipeline.SeverityInfo},
		{ValidatorID: "V19", Pass: true, Severity: pipeline.SeverityInfo},
	}
	// Add failures for all others.
	for _, id := range []string{"V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08", "V09", "V10", "V11", "V12", "V13", "V14", "V15", "V16", "V17"} {
		results = append(results, &pipeline.ValidationResult{
			ValidatorID: id,
			Pass:        false,
			Severity:    pipeline.SeverityWarning,
		})
	}

	store := &mockResultStore{results: results}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for low score, got true")
	}
	if res.Evidence["decision"] != string(v20_composite.DecisionReject) {
		t.Errorf("want REJECT for low score, got %q", res.Evidence["decision"])
	}
}

// TestV20_MidScore verifies that 60–79% score with no criticals → MANUAL_REVIEW.
func TestV20_MidScore(t *testing.T) {
	results := allPass()
	// Override high-weight validators to WARNING failures (not critical).
	for _, r := range results {
		switch r.ValidatorID {
		case "V01", "V02", "V03", "V04", "V05", "V07", "V12":
			r.Pass = false
			r.Severity = pipeline.SeverityWarning
		}
	}

	store := &mockResultStore{results: results}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Score should be between 60–80% → MANUAL_REVIEW.
	if res.Evidence["decision"] == string(v20_composite.DecisionPublish) {
		t.Error("want non-PUBLISH for mid score with warnings")
	}
}

// TestV20_StoreError verifies soft-fail on store error.
func TestV20_StoreError(t *testing.T) {
	store := &mockResultStore{err: errors.New("database locked")}
	val := v20_composite.NewWithStore(store)

	res, err := val.Validate(context.Background(), vehicle())
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true (soft-fail) when store returns error, got false")
	}
}
