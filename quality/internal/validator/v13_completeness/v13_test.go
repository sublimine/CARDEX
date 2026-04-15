package v13_completeness_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v13_completeness"
)

func photos(n int) []string {
	urls := make([]string, n)
	for i := range urls {
		urls[i] = "https://cdn.example.com/photo.jpg"
	}
	return urls
}

// TestV13_FullVehicle verifies that a fully-populated vehicle scores 100 and passes.
func TestV13_FullVehicle(t *testing.T) {
	val := v13_completeness.New()
	v := &pipeline.Vehicle{
		InternalID:   "T1",
		VIN:          "WBA3A5C51DF358058",
		Make:         "BMW",
		Model:        "320d",
		Year:         2020,
		Mileage:      45000,
		PriceEUR:     28500,
		Fuel:         "Diesel",
		Transmission: "Automatic",
		Title:        "BMW 320d Sport Line 2020",
		PhotoURLs:    photos(8),
	}
	res, err := val.Validate(context.Background(), v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for full vehicle, issue: %s", res.Issue)
	}
	if res.Evidence["score"] != "100/100" {
		t.Errorf("want score 100/100, got %q", res.Evidence["score"])
	}
}

// TestV13_MissingPhotosAndPrice verifies score is acceptably high without photos+price (75).
func TestV13_MissingPhotosAndPrice(t *testing.T) {
	// Missing: Photos (10pts), PriceEUR (15pts) → score = 100 - 25 = 75
	val := v13_completeness.New()
	v := &pipeline.Vehicle{
		InternalID:   "T2",
		VIN:          "WBA3A5C51DF358058",
		Make:         "BMW",
		Model:        "320d",
		Year:         2020,
		Mileage:      45000,
		Fuel:         "Diesel",
		Transmission: "Automatic",
		Title:        "BMW 320d Sport Line 2020",
		// No photos, no price
	}
	res, err := val.Validate(context.Background(), v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for score 75 (acceptable), issue: %s", res.Issue)
	}
	if res.Evidence["score"] != "75/100" {
		t.Errorf("want score 75/100, got %q", res.Evidence["score"])
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for score 75, got %s", res.Severity)
	}
}

// TestV13_MissingMakeModelYear verifies score < 50 produces WARNING.
func TestV13_MissingMakeModelYear(t *testing.T) {
	// Missing: VIN(20), Make(10), Model(10), Year(10) → score = 100-50 = 50... hmm
	// Let's make it really sparse: only Mileage(10) + Title(5) = 15 → WARNING
	val := v13_completeness.New()
	v := &pipeline.Vehicle{
		InternalID: "T3",
		Mileage:    45000,
		Title:      "Some car",
		// No VIN, make, model, year, price, fuel, transmission, photos
	}
	res, err := val.Validate(context.Background(), v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Errorf("want pass=false for low score, got true (score: %s)", res.Evidence["score"])
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for low score, got %s", res.Severity)
	}
	if res.Suggested["fields_to_add"] == "" {
		t.Error("want suggested fields list for low score")
	}
}

// TestV13_OnlyVIN verifies that a VIN-only record scores 20 (WARNING).
func TestV13_OnlyVIN(t *testing.T) {
	val := v13_completeness.New()
	v := &pipeline.Vehicle{
		InternalID: "T4",
		VIN:        "WBA3A5C51DF358058",
	}
	res, err := val.Validate(context.Background(), v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for VIN-only record (score 20)")
	}
	if res.Evidence["score"] != "20/100" {
		t.Errorf("want score 20/100, got %q", res.Evidence["score"])
	}
}

// TestV13_ScoreConfidence verifies confidence is proportional to score.
func TestV13_ScoreConfidence(t *testing.T) {
	val := v13_completeness.New()
	v := &pipeline.Vehicle{
		InternalID:   "T5",
		VIN:          "WBA3A5C51DF358058",
		Make:         "BMW",
		Model:        "320d",
		Year:         2020,
		Mileage:      45000,
		PriceEUR:     28500,
		Fuel:         "Diesel",
		Transmission: "Automatic",
		Title:        "BMW 320d",
		PhotoURLs:    photos(3),
	}
	res, err := val.Validate(context.Background(), v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Confidence != 1.0 {
		t.Errorf("want confidence 1.0 for score 100, got %f", res.Confidence)
	}
}
