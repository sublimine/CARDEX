package v04_nlp_makemodel_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v04_nlp_makemodel"
)

func vehicle(make_, model, title string) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID: "T1",
		Make:       make_,
		Model:      model,
		Title:      title,
	}
}

// TestV04_StandardTitle verifies that a standard dealer title passes with
// high confidence when both make and model are present.
func TestV04_StandardTitle(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "320i", "BMW 320i Sport Line 2020 48000km"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for standard title, issue: %s", res.Issue)
	}
	if res.Confidence < 0.9 {
		t.Errorf("want confidence >= 0.9 for exact match, got %f", res.Confidence)
	}
}

// TestV04_FuzzyTypo verifies that a common OCR/copy-paste typo ("BMV") is
// handled by Levenshtein fuzzy matching and the result passes.
func TestV04_FuzzyTypo(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "320", "BMV 320 sport 2020"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for fuzzy typo 'BMV'→'BMW', issue: %s", res.Issue)
	}
	// Fuzzy match should have lower confidence than exact.
	if res.Confidence >= 1.0 {
		t.Errorf("want confidence < 1.0 for fuzzy match, got %f", res.Confidence)
	}
}

// TestV04_MakeAbsent verifies that a title without the make produces a WARNING failure.
func TestV04_MakeAbsent(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "320i", "Voiture occasion 320i diesel 2020"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// "BMW" is not in title — but "320i" is, so model matched but make absent.
	if res.Pass {
		t.Errorf("want pass=false when make absent from title, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want severity WARNING, got %s", res.Severity)
	}
}

// TestV04_NeitherMakeNorModel verifies total absence of make+model produces failure.
func TestV04_NeitherMakeNorModel(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "M5", "Voiture de sport premium automatique"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false when neither make nor model in title")
	}
	if res.Confidence > 0.2 {
		t.Errorf("want low confidence for no match, got %f", res.Confidence)
	}
}

// TestV04_NoTitle verifies that a missing title is skipped with INFO.
func TestV04_NoTitle(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "320i", ""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true (skip) for empty title")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO severity for skipped check, got %s", res.Severity)
	}
}

// TestV04_MultiWordModel verifies multi-word models like "3 Series" are matched
// when both tokens appear in the title.
func TestV04_MultiWordModel(t *testing.T) {
	val := v04_nlp_makemodel.New()
	res, err := val.Validate(context.Background(),
		vehicle("BMW", "3 Series", "BMW 3 Series 2021 Sedan 320d"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for multi-word model '3 Series', issue: %s", res.Issue)
	}
}
