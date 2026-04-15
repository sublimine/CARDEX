package v11_nlg_quality_test

import (
	"context"
	"strings"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v11_nlg_quality"
)

func vehicle(make_, model, country, desc string) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID:    "T1",
		Make:          make_,
		Model:         model,
		SourceCountry: country,
		Description:   desc,
	}
}

// TestV11_GoodDescription verifies a proper description passes.
func TestV11_GoodDescription(t *testing.T) {
	val := v11_nlg_quality.New()
	desc := "BMW 320d, excellent condition, full service history. Leather seats, panoramic sunroof, " +
		"navigation system. One owner from new. Located in Munich."
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "DE", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for good description, issue: %s", res.Issue)
	}
}

// TestV11_TooShort verifies that a very short description produces a WARNING.
func TestV11_TooShort(t *testing.T) {
	val := v11_nlg_quality.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "DE", "Good car."))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for short description, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for short description, got %s", res.Severity)
	}
}

// TestV11_RepeatedSentences verifies that a repeated sentence produces a WARNING.
func TestV11_RepeatedSentences(t *testing.T) {
	val := v11_nlg_quality.New()
	sentence := "This vehicle is in excellent condition and ready for the road"
	desc := strings.Repeat(sentence+". ", 4)
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for repeated sentences, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for repetition, got %s", res.Severity)
	}
}

// TestV11_LoremIpsum verifies that a lorem-ipsum placeholder is CRITICAL.
func TestV11_LoremIpsum(t *testing.T) {
	val := v11_nlg_quality.New()
	desc := "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor"
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for lorem ipsum, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for lorem ipsum, got %s", res.Severity)
	}
}

// TestV11_LanguageMismatch verifies that a French description for a DE vehicle is WARNING.
func TestV11_LanguageMismatch(t *testing.T) {
	val := v11_nlg_quality.New()
	// French description for a German-market vehicle
	desc := "BMW 320d en très bon état avec un historique complet. Équipement de luxe, " +
		"sièges en cuir, toit ouvrant. Premier propriétaire. Situé à Paris."
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "DE", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Errorf("want pass=false for language mismatch (FR desc on DE vehicle)")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for language mismatch, got %s", res.Severity)
	}
}

// TestV11_MissingMakeModel verifies that a description without make+model is WARNING.
func TestV11_MissingMakeModel(t *testing.T) {
	val := v11_nlg_quality.New()
	desc := "Great car in excellent condition. Full service history available. Low mileage for age."
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false when make/model absent from description")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for missing make/model, got %s", res.Severity)
	}
}

// TestV11_EmptyDescription verifies that missing description is INFO (not a failure).
func TestV11_EmptyDescription(t *testing.T) {
	val := v11_nlg_quality.New()
	res, err := val.Validate(context.Background(), vehicle("BMW", "320d", "DE", ""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true (INFO skip) for empty description")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for empty description, got %s", res.Severity)
	}
}
