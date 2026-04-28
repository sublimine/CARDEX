// Package v18_language_consistency implements validation strategy V18 — Language Consistency.
//
// # Strategy
//
// A vehicle listing's description language should match the expected language(s) for
// its source country. A German-market listing in Spanish is likely a scraping artefact,
// a copy-paste fraud, or a metadata error.
//
// # Country → Expected Languages
//
//   - DE, AT       → [de, en]
//   - FR           → [fr, en]
//   - BE           → [fr, nl, de, en]   (trilingual country)
//   - CH           → [de, fr, it, en]   (quadrilingual country)
//   - ES           → [es, en]
//   - IT           → [it, en]
//   - NL           → [nl, en]
//   - GB, IE       → [en]
//   - Other/unknown→ skip check (INFO)
//
// English is always an accepted secondary language because many EU dealers publish
// dual-language listings.
//
// # Detection method
//
// Stopword frequency matching across 6 language profiles (identical to V11):
// the language whose stopwords appear most frequently wins, subject to a minimum
// count of 2 to avoid false positives on very short texts.
//
// An empty description → skip (V13 completeness handles missing fields).
// Inconclusive detection → INFO (not enough text to decide).
package v18_language_consistency

import (
	"context"
	"fmt"
	"strings"
	"unicode"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V18"
	strategyName = "Language Consistency"

	minStopwordHits = 2 // minimum stopword matches to consider detection conclusive
)

// languageStopwords maps ISO 639-1 code to characteristic stopwords.
var languageStopwords = map[string][]string{
	"de": {"und", "der", "die", "das", "ein", "ist", "mit", "von", "auf", "bei", "für", "nicht", "auch"},
	"fr": {"le", "la", "les", "de", "du", "un", "une", "est", "avec", "pour", "sur", "dans", "qui"},
	"es": {"el", "la", "los", "de", "del", "un", "una", "es", "con", "por", "para", "este", "esta"},
	"it": {"il", "lo", "la", "di", "del", "un", "una", "con", "per", "che", "sono", "questo"},
	"en": {"the", "and", "for", "with", "this", "that", "has", "have", "are", "from", "our", "its"},
	"nl": {"de", "het", "een", "van", "met", "voor", "dit", "dat", "zijn", "heeft", "ook", "door"},
}

// countryExpectedLangs maps ISO-3166-1 alpha-2 country code to the set of accepted language codes.
// English is universally accepted because many EU dealers publish dual-language listings.
var countryExpectedLangs = map[string][]string{
	"DE": {"de", "en"},
	"AT": {"de", "en"},
	"CH": {"de", "fr", "it", "en"},
	"FR": {"fr", "en"},
	"BE": {"fr", "nl", "de", "en"},
	"ES": {"es", "en"},
	"IT": {"it", "en"},
	"NL": {"nl", "en"},
	"GB": {"en"},
	"IE": {"en"},
	"LU": {"fr", "de", "en"},
	"PT": {"pt", "en"},
	"PL": {"pl", "en"},
	"CZ": {"cs", "en"},
	"SK": {"sk", "en"},
	"HU": {"hu", "en"},
	"RO": {"ro", "en"},
}

// LangConsistency implements pipeline.Validator for V18.
type LangConsistency struct{}

// New returns a LangConsistency validator.
func New() *LangConsistency { return &LangConsistency{} }

func (v *LangConsistency) ID() string                  { return strategyID }
func (v *LangConsistency) Name() string                { return strategyName }
func (v *LangConsistency) Severity() pipeline.Severity { return pipeline.SeverityWarning }

// Validate detects the description language and verifies it against the source country.
func (v *LangConsistency) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	desc := strings.TrimSpace(vehicle.Description)
	if desc == "" {
		result.Pass = true
		result.Issue = "no description to check (V13 tracks completeness)"
		result.Confidence = 1.0
		return result, nil
	}

	country := strings.ToUpper(strings.TrimSpace(vehicle.SourceCountry))
	if country == "" {
		result.Pass = true
		result.Issue = "no SourceCountry — skipping language check"
		result.Confidence = 1.0
		return result, nil
	}

	expected, ok := countryExpectedLangs[country]
	if !ok {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("country %q not in language map — skipping check", country)
		result.Confidence = 1.0
		return result, nil
	}

	detected := detectLanguage(strings.ToLower(desc))
	result.Evidence["country"] = country
	result.Evidence["expected_langs"] = strings.Join(expected, ",")

	if detected == "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "language detection inconclusive (too little text)"
		result.Confidence = 0.5
		return result, nil
	}

	result.Evidence["detected_lang"] = detected

	for _, lang := range expected {
		if lang == detected {
			result.Pass = true
			result.Confidence = 0.9
			return result, nil
		}
	}

	result.Pass = false
	result.Severity = pipeline.SeverityWarning
	result.Issue = fmt.Sprintf("description language %q does not match expected %v for country %s",
		detected, expected, country)
	result.Confidence = 0.85
	result.Suggested["action"] = "verify description language matches source market"
	return result, nil
}

// detectLanguage returns the most likely ISO 639-1 language code for textLower,
// based on stopword frequency matching. Returns "" if inconclusive.
func detectLanguage(textLower string) string {
	words := strings.FieldsFunc(textLower, func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
	wordSet := make(map[string]bool, len(words))
	for _, w := range words {
		wordSet[w] = true
	}

	best, bestCount := "", 0
	for lang, stops := range languageStopwords {
		count := 0
		for _, s := range stops {
			if wordSet[s] {
				count++
			}
		}
		if count > bestCount {
			bestCount = count
			best = lang
		}
	}
	if bestCount < minStopwordHits {
		return ""
	}
	return best
}
