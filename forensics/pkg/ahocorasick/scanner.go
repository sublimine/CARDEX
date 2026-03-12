// Package ahocorasick provides pattern matching for margin-scheme tax classification.
// Matches keywords that indicate REBU (Regime des Biens Usagés) tax status.
package ahocorasick

import "strings"

// marginSchemePatterns are the preloaded keywords for instant REBU classification.
var marginSchemePatterns = []string{
	"§25a",
	"differenzbesteuerung",
	"margeregling",
	"margeregeling",
	"regime del margine",
	"régimen especial de bienes usados",
	"margin scheme",
	"marge",
	"ustg",
	"second-hand goods",
}

// Scanner matches margin-scheme keywords in text for tax classification.
type Scanner struct {
	patterns []string
}

// New creates a Scanner with preloaded margin-scheme patterns.
func New() *Scanner {
	patterns := make([]string, len(marginSchemePatterns))
	for i, p := range marginSchemePatterns {
		patterns[i] = strings.ToLower(p)
	}
	return &Scanner{patterns: patterns}
}

// Scan checks if text contains any margin-scheme keyword.
// Text is converted to lowercase before scanning.
// Returns (true, keyword) on first match, (false, "") if no match.
func (s *Scanner) Scan(text string) (matched bool, keyword string) {
	lower := strings.ToLower(text)
	for i, p := range s.patterns {
		if strings.Contains(lower, p) {
			return true, marginSchemePatterns[i]
		}
	}
	return false, ""
}
