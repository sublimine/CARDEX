package ner_test

import (
	"testing"

	"cardex.eu/discovery/internal/families/familia_o/ner"
)

func TestExtractCandidates_GermanAutohaus(t *testing.T) {
	text := `Der Automobilhändler Autohaus Muster GmbH hat heute eine neue Filiale in Berlin eröffnet.
Auch Autohaus Schneider AG plant einen Ausbau im nächsten Quartal.`

	candidates := ner.ExtractCandidates(text)
	if len(candidates) == 0 {
		t.Fatal("want at least one candidate, got none")
	}

	names := make(map[string]bool)
	for _, c := range candidates {
		names[c.Normalized] = true
	}
	if !names["muster"] {
		t.Errorf("want 'muster' in normalized candidates, got %v", candidates)
	}
}

func TestExtractCandidates_FrenchGarage(t *testing.T) {
	text := `Le Garage Dupont SARL a été racheté par Garage Martin SAS.
L'opération porte sur deux concessions en Île-de-France.`

	candidates := ner.ExtractCandidates(text)
	if len(candidates) == 0 {
		t.Fatal("want at least one candidate, got none")
	}
	names := make(map[string]bool)
	for _, c := range candidates {
		names[c.Normalized] = true
	}
	if !names["dupont"] && !names["martin"] {
		t.Errorf("want 'dupont' or 'martin', got %v", candidates)
	}
}

func TestExtractCandidates_NoMatches(t *testing.T) {
	text := "The weather in Berlin was sunny yesterday. No dealers mentioned here."
	candidates := ner.ExtractCandidates(text)
	// Non-automotive text must not produce high-confidence dealer candidates.
	// Zero is expected; up to 3 spurious matches is tolerable.
	// More than 3 means the NER heuristic is too aggressive.
	if len(candidates) > 3 {
		t.Errorf("expected ≤3 spurious candidates for non-dealer text, got %d: %v",
			len(candidates), candidates)
	}
}

func TestNormalize_StripsLegalSuffixes(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"Autohaus Muster GmbH", "muster"},
		{"Garage Dupont SARL", "dupont"},
		{"Talleres García SL", "garcía"},
		{"Mueller Motors", "mueller motors"},
	}
	for _, tc := range cases {
		got := ner.Normalize(tc.in)
		if got != tc.want {
			t.Errorf("Normalize(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestExtractCandidates_Deduplication(t *testing.T) {
	// Same entity mentioned twice should appear only once.
	text := `Autohaus Muster GmbH hat eine neue Filiale eröffnet.
Laut Geschäftsführer der Autohaus Muster GmbH verlaufen die Geschäfte gut.`

	candidates := ner.ExtractCandidates(text)
	count := 0
	for _, c := range candidates {
		if c.Normalized == "muster" {
			count++
		}
	}
	if count > 1 {
		t.Errorf("want at most 1 occurrence of 'muster', got %d", count)
	}
}
