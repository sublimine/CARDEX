package v18_language_consistency_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v18_language_consistency"
)

func vehicle(country, description string) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID:    "T1",
		SourceCountry: country,
		Description:   description,
	}
}

// TestV18_MatchingLanguage_DE verifies German description for German vehicle passes.
func TestV18_MatchingLanguage_DE(t *testing.T) {
	val := v18_language_consistency.New()
	desc := "Das Fahrzeug ist in sehr gutem Zustand. Mit Klimaanlage und Automatikgetriebe. Die Ausstattung ist komplett und das Auto ist scheckheftgepflegt."
	res, err := val.Validate(context.Background(), vehicle("DE", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for DE description on DE vehicle, issue: %s", res.Issue)
	}
	if res.Evidence["detected_lang"] != "de" {
		t.Errorf("want detected_lang=de, got %q", res.Evidence["detected_lang"])
	}
}

// TestV18_MismatchedLanguage verifies Spanish description for German vehicle → WARNING.
func TestV18_MismatchedLanguage(t *testing.T) {
	val := v18_language_consistency.New()
	// Clearly Spanish text
	desc := "El vehículo está en muy buen estado. Con aire acondicionado y transmisión automática. Este coche es una buena compra para la familia."
	res, err := val.Validate(context.Background(), vehicle("DE", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Errorf("want pass=false for ES description on DE vehicle")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING, got %s", res.Severity)
	}
}

// TestV18_EnglishAccepted verifies English description is accepted for any country.
func TestV18_EnglishAccepted(t *testing.T) {
	val := v18_language_consistency.New()
	desc := "This vehicle is in excellent condition. With air conditioning and automatic transmission. The car has full service history and has been well maintained."
	res, err := val.Validate(context.Background(), vehicle("DE", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for EN description on DE vehicle (EN is always accepted), issue: %s", res.Issue)
	}
}

// TestV18_MultilingualCountry verifies CH accepts German, French, or Italian.
func TestV18_MultilingualCountry(t *testing.T) {
	val := v18_language_consistency.New()
	// French description for CH vehicle should pass.
	desc := "Le véhicule est en très bon état. Avec climatisation et transmission automatique. La voiture est bien entretenue et prête pour la route."
	res, err := val.Validate(context.Background(), vehicle("CH", desc))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for FR description on CH vehicle, issue: %s", res.Issue)
	}
}

// TestV18_EmptyDescription passes (V13 handles completeness).
func TestV18_EmptyDescription(t *testing.T) {
	val := v18_language_consistency.New()
	res, err := val.Validate(context.Background(), vehicle("DE", ""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for empty description, got false: %s", res.Issue)
	}
}

// TestV18_UnknownCountry skips check and passes INFO.
func TestV18_UnknownCountry(t *testing.T) {
	val := v18_language_consistency.New()
	res, err := val.Validate(context.Background(), vehicle("XX", "some text about a car"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for unknown country, got false: %s", res.Issue)
	}
}
