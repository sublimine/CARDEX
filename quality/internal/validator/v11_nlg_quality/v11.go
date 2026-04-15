// Package v11_nlg_quality implements validation strategy V11 — NLG Description Quality.
//
// # Checks (in order of severity)
//
//  1. Generic-phrase blacklist: "lorem ipsum", "describe vehicle here", "tbd", "todo",
//     "placeholder" → CRITICAL (unfilled template marker)
//  2. Description length < 50 chars → WARNING (too short to be informative)
//  3. Sentence repetition: any sentence appearing > 2× → WARNING (NLG loop artifact)
//  4. Language consistency: inferred language vs SourceCountry expected language → WARNING
//  5. Make/model mention: description should reference the vehicle's make and model → WARNING
//
// Empty description is treated as INFO (nothing to check; V13 completeness handles missing fields).
//
// Severity: CRITICAL for template markers; WARNING for quality issues.
package v11_nlg_quality

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"unicode"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V11"
	strategyName = "NLG Description Quality"

	minDescLen       = 50
	maxRepeatSent    = 2
)

// genericPhrases are unfilled template markers that indicate the description
// was never properly authored.
var genericPhrases = []string{
	"lorem ipsum",
	"describe vehicle here",
	"tbd",
	"todo",
	"placeholder",
	"insert description",
	"vehicle description here",
	"beschreibung hier",
	"description à compléter",
}

// languageStopwords maps language codes to characteristic stopwords.
var languageStopwords = map[string][]string{
	"de": {"und", "der", "die", "das", "ein", "ist", "mit", "von", "auf", "bei", "für", "nicht", "auch"},
	"fr": {"le", "la", "les", "de", "du", "un", "une", "est", "avec", "pour", "sur", "dans", "qui"},
	"es": {"el", "la", "los", "de", "del", "un", "una", "es", "con", "por", "para", "este", "esta"},
	"it": {"il", "lo", "la", "di", "del", "un", "una", "con", "per", "che", "sono", "questo"},
	"en": {"the", "and", "for", "with", "this", "that", "has", "have", "are", "from", "our", "its"},
	"nl": {"de", "het", "een", "van", "met", "voor", "dit", "dat", "zijn", "heeft", "ook", "door"},
}

// countryToLang maps ISO-3166-1 country codes to expected language codes.
var countryToLang = map[string]string{
	"DE": "de", "AT": "de", "CH": "de",
	"FR": "fr", "BE": "fr",
	"ES": "es",
	"IT": "it",
	"GB": "en", "IE": "en", "US": "en", "AU": "en",
	"NL": "nl",
}

var sentenceSplitter = regexp.MustCompile(`[.!?]+`)
var nonAlphaRE = regexp.MustCompile(`[^a-z0-9 ]+`)

// NLGQuality implements pipeline.Validator for V11.
type NLGQuality struct{}

// New returns an NLGQuality validator.
func New() *NLGQuality { return &NLGQuality{} }

func (v *NLGQuality) ID() string                 { return strategyID }
func (v *NLGQuality) Name() string               { return strategyName }
func (v *NLGQuality) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the vehicle's description for quality issues.
func (v *NLGQuality) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityWarning,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	desc := strings.TrimSpace(vehicle.Description)

	if desc == "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no description to validate (V13 completeness tracks missing fields)"
		result.Confidence = 1.0
		return result, nil
	}

	result.Evidence["desc_length"] = fmt.Sprintf("%d", len(desc))
	descLower := strings.ToLower(desc)

	// 1. Generic phrase blacklist.
	for _, phrase := range genericPhrases {
		if strings.Contains(descLower, phrase) {
			result.Pass = false
			result.Severity = pipeline.SeverityCritical
			result.Issue = fmt.Sprintf("description contains template marker: %q", phrase)
			result.Confidence = 1.0
			result.Suggested["Description"] = "replace with actual vehicle description"
			return result, nil
		}
	}

	var warnings []string

	// 2. Length check.
	if len(desc) < minDescLen {
		warnings = append(warnings, fmt.Sprintf("description too short: %d chars (min %d)", len(desc), minDescLen))
	}

	// 3. Sentence repetition.
	if rep := findRepetition(desc); rep != "" {
		warnings = append(warnings, fmt.Sprintf("repeated sentence (NLG artifact): %q", rep))
		result.Evidence["repeated_sentence"] = rep
	}

	// 4. Language consistency.
	if vehicle.SourceCountry != "" {
		expectedLang := countryToLang[strings.ToUpper(vehicle.SourceCountry)]
		if expectedLang != "" {
			detectedLang := detectLanguage(descLower)
			result.Evidence["detected_lang"] = detectedLang
			result.Evidence["expected_lang"] = expectedLang
			if detectedLang != "" && detectedLang != expectedLang {
				warnings = append(warnings, fmt.Sprintf("language mismatch: detected %q, expected %q for country %s",
					detectedLang, expectedLang, vehicle.SourceCountry))
			}
		}
	}

	// 5. Make/model mention.
	if vehicle.Make != "" || vehicle.Model != "" {
		makePresent := vehicle.Make == "" || strings.Contains(descLower, strings.ToLower(vehicle.Make))
		modelPresent := vehicle.Model == "" || strings.Contains(descLower, strings.ToLower(vehicle.Model))
		if !makePresent || !modelPresent {
			missing := []string{}
			if !makePresent {
				missing = append(missing, "make ("+vehicle.Make+")")
			}
			if !modelPresent {
				missing = append(missing, "model ("+vehicle.Model+")")
			}
			warnings = append(warnings, "description does not mention "+strings.Join(missing, ", "))
		}
	}

	if len(warnings) > 0 {
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = strings.Join(warnings, "; ")
		result.Confidence = 0.85
		return result, nil
	}

	result.Pass = true
	result.Severity = pipeline.SeverityInfo
	result.Confidence = 0.9
	return result, nil
}

// findRepetition returns the first sentence that appears more than maxRepeatSent times,
// or "" if none found.
func findRepetition(text string) string {
	parts := sentenceSplitter.Split(text, -1)
	counts := make(map[string]int)
	for _, p := range parts {
		norm := strings.TrimSpace(strings.ToLower(p))
		norm = nonAlphaRE.ReplaceAllString(norm, " ")
		norm = strings.Join(strings.Fields(norm), " ")
		if len(norm) < 10 {
			continue // ignore very short fragments
		}
		counts[norm]++
		if counts[norm] > maxRepeatSent {
			// Return the original (untrimmed) fragment for the evidence.
			return strings.TrimSpace(p)
		}
	}
	return ""
}

// detectLanguage returns the most likely language code for the given text,
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
	if bestCount < 2 {
		return "" // inconclusive
	}
	return best
}
