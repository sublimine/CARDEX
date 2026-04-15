package v19_currency_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v19_currency"
)

func vehicle(country string, priceEUR int) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID:    "T1",
		SourceCountry: country,
		PriceEUR:      priceEUR,
	}
}

// TestV19_ZeroPrice verifies that zero price → CRITICAL.
func TestV19_ZeroPrice(t *testing.T) {
	val := v19_currency.New()
	res, err := val.Validate(context.Background(), vehicle("DE", 0))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for zero price, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for zero price, got %s", res.Severity)
	}
}

// TestV19_NegativePrice verifies that negative price → CRITICAL.
func TestV19_NegativePrice(t *testing.T) {
	val := v19_currency.New()
	res, err := val.Validate(context.Background(), vehicle("DE", -500))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for negative price, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for negative price, got %s", res.Severity)
	}
}

// TestV19_OverMillionPrice verifies that price > 1,000,000 → WARNING.
func TestV19_OverMillionPrice(t *testing.T) {
	val := v19_currency.New()
	res, err := val.Validate(context.Background(), vehicle("DE", 1_500_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for price > 1M EUR, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for >1M price, got %s", res.Severity)
	}
}

// TestV19_SwissListingInfo verifies CH + reasonable price → INFO note (still passes).
func TestV19_SwissListingInfo(t *testing.T) {
	val := v19_currency.New()
	res, err := val.Validate(context.Background(), vehicle("CH", 25_000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for CH price (INFO note), got false: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO severity for CH CHF note, got %s", res.Severity)
	}
	if res.Evidence["chf_note"] != "true" {
		t.Errorf("want chf_note evidence for CH listing, got %q", res.Evidence["chf_note"])
	}
}

// TestV19_ValidPrice verifies that a normal EUR price passes cleanly.
func TestV19_ValidPrice(t *testing.T) {
	val := v19_currency.New()
	res, err := val.Validate(context.Background(), vehicle("DE", 18_500))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for valid price, got false: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO (no issue) for valid price, got %s", res.Severity)
	}
}
