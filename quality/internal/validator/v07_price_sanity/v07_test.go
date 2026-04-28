package v07_price_sanity_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v07_price_sanity"
)

func vehicle(make_, model string, year, priceEUR int) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID: "T1",
		Make:       make_,
		Model:      model,
		Year:       year,
		PriceEUR:   priceEUR,
	}
}

// TestV07_BMW_NormalPrice verifies that a BMW 320d 2020 at market price passes.
func TestV07_BMW_NormalPrice(t *testing.T) {
	val := v07_price_sanity.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", 2020, 29000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for BMW 320d 2020 at €29000, issue: %s", res.Issue)
	}
}

// TestV07_BMW_AnomalyLow verifies that €100 for a BMW 320i 2020 is CRITICAL.
func TestV07_BMW_AnomalyLow(t *testing.T) {
	val := v07_price_sanity.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "320i", 2020, 100))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for €100 BMW 320i, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for impossibly low price, got %s", res.Severity)
	}
}

// TestV07_Clio_Normal verifies that a Renault Clio 2018 at €8000 passes.
func TestV07_Clio_Normal(t *testing.T) {
	val := v07_price_sanity.New()
	res, err := val.Validate(context.Background(), vehicle("Renault", "Clio", 2018, 8000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for Renault Clio 2018 €8000, issue: %s", res.Issue)
	}
}

// TestV07_UnknownMake_Info verifies that an unknown make/model returns INFO.
func TestV07_UnknownMake_Info(t *testing.T) {
	val := v07_price_sanity.New()
	res, err := val.Validate(context.Background(), vehicle("Trabant", "601", 1985, 3500))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true (INFO) for unknown make, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for unknown make, got %s", res.Severity)
	}
}

// TestV07_ZeroPrice_Critical verifies that a zero price is CRITICAL.
func TestV07_ZeroPrice_Critical(t *testing.T) {
	val := v07_price_sanity.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "3 Series", 2020, 0))
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

// TestV07_PriceHighWarning verifies that an excessively high price is WARNING.
func TestV07_PriceHighWarning(t *testing.T) {
	val := v07_price_sanity.New()
	// BMW 3 Series p75 ~= €38000 for 2018-2021. p75*2 = €76000.
	res, err := val.Validate(context.Background(), vehicle("BMW", "3 Series", 2020, 90000))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for excessively high price, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for high price, got %s", res.Severity)
	}
}
