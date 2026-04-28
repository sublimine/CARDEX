package v08_mileage_sanity_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v08_mileage_sanity"
)

const refYear = 2026 // fixed reference year for deterministic tests

func vehicle(year, mileage int) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", Year: year, Mileage: mileage}
}

// TestV08_Normal verifies that a 2-year-old car with 50k km passes.
func TestV08_Normal(t *testing.T) {
	val := v08_mileage_sanity.NewWithYear(refYear)
	// 2024 car (age=2), 50k km — within 2*20000*2.5=100k upper bound
	res, err := val.Validate(context.Background(), vehicle(2024, 50_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 50k km on 2-year-old, issue: %s", res.Issue)
	}
}

// TestV08_SuspiciousLowMileage verifies that <100 km on a 10-year-old car is CRITICAL.
func TestV08_SuspiciousLowMileage(t *testing.T) {
	val := v08_mileage_sanity.NewWithYear(refYear)
	// 2016 car (age=10), 50 km — odometer rollback suspicion
	res, err := val.Validate(context.Background(), vehicle(2016, 50))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 50 km on 10-year-old, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for suspicious low mileage, got %s", res.Severity)
	}
}

// TestV08_ExcessiveMileage verifies that 800k km is CRITICAL.
func TestV08_ExcessiveMileage(t *testing.T) {
	val := v08_mileage_sanity.NewWithYear(refYear)
	res, err := val.Validate(context.Background(), vehicle(2015, 800_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 800k km, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 800k km, got %s", res.Severity)
	}
}

// TestV08_HighMileageWarning verifies that an 8-year-old car with 200k km passes
// (within the 2.5× upper bound of 8×20000×2.5=400k).
func TestV08_HighMileageWarning(t *testing.T) {
	val := v08_mileage_sanity.NewWithYear(refYear)
	// 2018 car (age=8), 200k km — 8*20000*2.5=400k, so 200k is within bounds
	res, err := val.Validate(context.Background(), vehicle(2018, 200_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 200k km on 8-year-old (within upper bound), issue: %s", res.Issue)
	}
}

// TestV08_AboveUpperBound verifies that a 3-year-old car with 200k km is WARNING.
func TestV08_AboveUpperBound(t *testing.T) {
	val := v08_mileage_sanity.NewWithYear(refYear)
	// 2023 car (age=3), 200k km — 3*20000*2.5=150k, so 200k exceeds upper
	res, err := val.Validate(context.Background(), vehicle(2023, 200_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 200k on 3-year-old car, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for above-upper-bound mileage, got %s", res.Severity)
	}
}
