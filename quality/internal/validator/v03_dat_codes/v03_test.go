package v03_dat_codes_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v03_dat_codes"
)

func vehicle(make_, model string, year int, datCode string) *pipeline.Vehicle {
	v := &pipeline.Vehicle{
		InternalID: "T1",
		Make:       make_,
		Model:      model,
		Year:       year,
	}
	if datCode != "" {
		v.Metadata = map[string]string{"dat_code": datCode}
	}
	return v
}

// TestV03_BMW_Match verifies that a BMW 320i with the correct DAT prefix passes.
func TestV03_BMW_Match(t *testing.T) {
	val := v03_dat_codes.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "320i", 2020, "BMW3XYZ"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for BMW 320i with BMW3 prefix, issue: %s", res.Issue)
	}
	if res.Confidence < 0.8 {
		t.Errorf("want confidence >= 0.8, got %f", res.Confidence)
	}
}

// TestV03_Toyota_Match verifies that a Toyota Prius with the correct DAT prefix passes.
func TestV03_Toyota_Match(t *testing.T) {
	val := v03_dat_codes.New()
	res, err := val.Validate(context.Background(), vehicle("Toyota", "Prius", 2019, "TYPRABC"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for Toyota Prius with TYPR prefix, issue: %s", res.Issue)
	}
}

// TestV03_Mismatch verifies that a wrong DAT prefix produces a WARNING failure.
func TestV03_Mismatch(t *testing.T) {
	val := v03_dat_codes.New()
	// BMW 3 Series should be BMW3*, but we pass MBC* (Mercedes C-Class prefix).
	res, err := val.Validate(context.Background(), vehicle("BMW", "3 Series", 2021, "MBCXYZ"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for DAT prefix mismatch, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want severity WARNING, got %s", res.Severity)
	}
	if res.Evidence["dat_prefix_expected"] == "" {
		t.Error("want evidence with expected DAT prefix")
	}
}

// TestV03_NoDATCode verifies that a vehicle without a DAT code is skipped (INFO pass).
func TestV03_NoDATCode(t *testing.T) {
	val := v03_dat_codes.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "3 Series", 2021, ""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true (skip) when no dat_code, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want severity INFO for skipped check, got %s", res.Severity)
	}
}

// TestV03_UnknownMakeModel verifies that an unknown make/model is skipped with INFO.
func TestV03_UnknownMakeModel(t *testing.T) {
	val := v03_dat_codes.New()
	res, err := val.Validate(context.Background(), vehicle("TRABANT", "601", 1988, "TR60XYZ"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for unknown make/model, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for unknown make/model, got %s", res.Severity)
	}
}
