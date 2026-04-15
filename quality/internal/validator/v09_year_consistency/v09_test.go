package v09_year_consistency_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v09_year_consistency"
)

const refYear = 2026

func vehicle(year int, title string, metadata map[string]string) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID: "T1",
		Year:       year,
		Title:      title,
		Metadata:   metadata,
	}
}

// TestV09_ValidYear verifies that 2023 passes cleanly.
func TestV09_ValidYear(t *testing.T) {
	val := v09_year_consistency.NewWithYear(refYear)
	res, err := val.Validate(context.Background(), vehicle(2023, "BMW 3 Series 2023 sedan", nil))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for year 2023, issue: %s", res.Issue)
	}
}

// TestV09_FutureYear_Critical verifies that year 2030 is CRITICAL.
func TestV09_FutureYear_Critical(t *testing.T) {
	val := v09_year_consistency.NewWithYear(refYear)
	res, err := val.Validate(context.Background(), vehicle(2030, "", nil))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for year 2030, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for future year, got %s", res.Severity)
	}
}

// TestV09_InvalidYear_Critical verifies that year 1850 is CRITICAL.
func TestV09_InvalidYear_Critical(t *testing.T) {
	val := v09_year_consistency.NewWithYear(refYear)
	res, err := val.Validate(context.Background(), vehicle(1850, "", nil))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for year 1850, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for year 1850, got %s", res.Severity)
	}
}

// TestV09_TitleYearMismatch verifies that a title year of 2018 vs extracted 2020 is WARNING.
func TestV09_TitleYearMismatch(t *testing.T) {
	val := v09_year_consistency.NewWithYear(refYear)
	// Vehicle year is 2020, but title says "2018"
	res, err := val.Validate(context.Background(), vehicle(2020, "BMW 320i 2018 diesel automatic", nil))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for title/year mismatch, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for title year mismatch, got %s", res.Severity)
	}
	if res.Evidence["title_year"] != "2018" {
		t.Errorf("want evidence title_year=2018, got %q", res.Evidence["title_year"])
	}
}

// TestV09_NHTSAYearMismatch verifies that NHTSA year mismatch in metadata produces WARNING.
func TestV09_NHTSAYearMismatch(t *testing.T) {
	val := v09_year_consistency.NewWithYear(refYear)
	res, err := val.Validate(context.Background(), vehicle(2020, "", map[string]string{
		"nhtsa_year": "2021",
	}))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for NHTSA year mismatch, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for NHTSA year mismatch, got %s", res.Severity)
	}
}
