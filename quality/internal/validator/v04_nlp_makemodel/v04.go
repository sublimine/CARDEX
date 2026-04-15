// Package v04_nlp_makemodel implements validation strategy V04 — NLP Make/Model
// from Title Cross-Validation.
//
// # Purpose
//
// Each vehicle record carries a raw title field extracted verbatim from the
// dealer listing (e.g. "BMW 320i Sport Line 2020 48tkm"). After structural
// extraction (E01–E12), the vehicle.Make and vehicle.Model fields are populated.
// V04 verifies that these derived fields actually appear in the source title,
// catching misclassification and OCR/copy-paste errors.
//
// # Algorithm
//
//  1. Normalize title, make, and model (lowercase, remove special chars).
//  2. Tokenise all three into word tokens.
//  3. Exact token match: does the title contain the make tokens? the model tokens?
//  4. If exact fails, try fuzzy: for each make/model token find the closest title
//     token by Levenshtein distance ≤ 2 (handles "BMV" → "BMW", "Clío" → "Clio").
//  5. Confidence is proportional to match quality (1.0 exact, 0.7 fuzzy).
//  6. If neither make nor model appears → WARNING failure.
//  7. If only one appears → WARNING with lower confidence.
//  8. Both appear → Pass.
//
// Severity: WARNING — a title mismatch may indicate a scraping error or
// misclassified listing, but not a fraudulent VIN.
package v04_nlp_makemodel

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"unicode"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V04"
	strategyName = "NLP Make/Model from Title"

	maxLevenshtein = 2 // maximum edit distance for fuzzy token match
)

var nonAlphaNum = regexp.MustCompile(`[^a-z0-9]+`)

// NLPMakeModel implements pipeline.Validator for V04.
type NLPMakeModel struct{}

// New returns an NLPMakeModel validator.
func New() *NLPMakeModel { return &NLPMakeModel{} }

func (v *NLPMakeModel) ID() string              { return strategyID }
func (v *NLPMakeModel) Name() string            { return strategyName }
func (v *NLPMakeModel) Severity() pipeline.Severity { return pipeline.SeverityWarning }

// Validate checks that the vehicle title contains the make and model tokens.
func (v *NLPMakeModel) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityWarning,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	title := strings.TrimSpace(vehicle.Title)
	make_ := strings.TrimSpace(vehicle.Make)
	model := strings.TrimSpace(vehicle.Model)

	// No title to check → INFO skip.
	if title == "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no title available for cross-validation"
		result.Confidence = 1.0
		return result, nil
	}
	// No make/model → INFO skip.
	if make_ == "" && model == "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no make/model to validate against title"
		result.Confidence = 1.0
		return result, nil
	}

	titleTokens := tokenize(title)
	result.Evidence["title_normalized"] = strings.Join(titleTokens, " ")

	makeMatched, makeConf := matchTokens(tokenize(make_), titleTokens)
	modelMatched, modelConf := matchTokens(tokenize(model), titleTokens)

	result.Evidence["make_matched"] = fmt.Sprintf("%v (conf %.2f)", makeMatched, makeConf)
	result.Evidence["model_matched"] = fmt.Sprintf("%v (conf %.2f)", modelMatched, modelConf)

	switch {
	case makeMatched && modelMatched:
		result.Pass = true
		result.Confidence = (makeConf + modelConf) / 2
	case makeMatched && !modelMatched:
		result.Pass = false
		result.Issue = fmt.Sprintf("model %q not found in title", model)
		result.Confidence = makeConf * 0.6
	case !makeMatched && modelMatched:
		result.Pass = false
		result.Issue = fmt.Sprintf("make %q not found in title", make_)
		result.Confidence = modelConf * 0.6
	default:
		result.Pass = false
		result.Issue = fmt.Sprintf("neither make %q nor model %q found in title %q", make_, model, title)
		result.Confidence = 0.1
	}
	return result, nil
}

// tokenize normalises a string and returns its word tokens.
// "BMW 3-Series" → ["bmw", "3", "series"]
func tokenize(s string) []string {
	s = strings.Map(func(r rune) rune {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return unicode.ToLower(r)
		}
		return ' '
	}, s)
	parts := strings.Fields(s)
	if len(parts) == 0 {
		return nil
	}
	return parts
}

// matchTokens returns whether every token in needles appears in haystack
// (either exactly or within Levenshtein distance 2), plus the average
// confidence (1.0 for exact, 0.7 for fuzzy).
func matchTokens(needles, haystack []string) (matched bool, confidence float64) {
	if len(needles) == 0 {
		return true, 1.0
	}

	totalConf := 0.0
	for _, needle := range needles {
		bestConf := 0.0
		for _, hay := range haystack {
			if needle == hay {
				bestConf = 1.0
				break
			}
			// Only attempt fuzzy matching on tokens long enough that a distance-2
			// edit cannot match arbitrary short words (e.g. "m5" ≠ "de").
			if len(needle) >= 3 && len(hay) >= 3 && lev(needle, hay) <= maxLevenshtein {
				bestConf = 0.7
			}
		}
		if bestConf == 0.0 {
			return false, 0.0
		}
		totalConf += bestConf
	}
	return true, totalConf / float64(len(needles))
}

// lev computes the Levenshtein edit distance between two strings.
// Uses the classic dynamic-programming algorithm (O(mn) time, O(min(m,n)) space).
func lev(a, b string) int {
	if a == b {
		return 0
	}
	ra, rb := []rune(a), []rune(b)
	if len(ra) > len(rb) {
		ra, rb = rb, ra
	}
	// ra is the shorter string.
	prev := make([]int, len(ra)+1)
	curr := make([]int, len(ra)+1)
	for i := range prev {
		prev[i] = i
	}
	for j := 1; j <= len(rb); j++ {
		curr[0] = j
		for i := 1; i <= len(ra); i++ {
			cost := 1
			if ra[i-1] == rb[j-1] {
				cost = 0
			}
			curr[i] = minInt(curr[i-1]+1, minInt(prev[i]+1, prev[i-1]+cost))
		}
		prev, curr = curr, prev
	}
	return prev[len(ra)]
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
