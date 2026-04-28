// Package ner implements a simple regex-based Named Entity Recognition pipeline
// for automotive dealer names. Used by O.1 (GDELT) and O.2 (RSS) to extract
// dealer candidates from unstructured article text.
//
// # Extraction strategy
//
// A set of language-sensitive regex patterns covers the main automotive entity
// forms across EU target countries:
//
//   - DE: "Autohaus Muster", "Autohaus Muster GmbH", "Muster KFZ GmbH"
//   - FR: "Garage Dupont", "Dupont Automobiles SAS"
//   - ES: "Concesionario García", "Talleres García SL"
//   - NL: "Autobedrijf de Jong BV"
//   - Generic: "Muster Motors", "BMW Autohaus Berlin"
//
// # Normalization
//
// Candidates are normalised (lowercased, legal suffix stripped, non-letter chars
// removed) before KG lookup to maximise match rate against the canonical
// normalized_name field in dealer_entity.
package ner

import (
	"regexp"
	"strings"
	"unicode"
)

// Candidate is a dealer name extracted from article text.
type Candidate struct {
	Raw        string // original extracted string
	Normalized string // normalized form for KG lookup
}

// patterns is the ordered list of regex rules. Each captures a dealer name.
// Order matters: more specific patterns are listed first to avoid duplicates
// from the generic catch-all at the end.
var patterns = []*regexp.Regexp{
	// German: "Autohaus Muster GmbH & Co. KG"
	regexp.MustCompile(`(?i)Autohaus\s+[A-ZÜÄÖ][a-züäöß][\w\s\-äüöÄÜÖß]{1,50}?(?:\s+(?:GmbH(?:\s+&\s+Co\.?\s+KG)?|AG|KG|OHG|e\.K\.|GbR))?(?:\s|,|\.|$)`),
	// German: "Muster KFZ GmbH" / "Müller Auto AG"
	regexp.MustCompile(`[A-ZÜÄÖ][a-züäöß]{2,20}(?:\s+[A-ZÜÄÖ][a-züäöß]{2,20}){0,2}\s+(?:KFZ|Kfz|Auto(?:haus|handel|center)?|PKW|Fahrzeug)\s+(?:GmbH|AG|KG)`),
	// French: "Garage Dupont" / "Garage du Marché SARL"
	regexp.MustCompile(`(?i)Garage\s+[A-ZÀ-Ö][a-zà-ö]{2,}[\w\s\-À-ö]{0,40}?(?:\s+(?:SAS|SARL|SA|SNC))?(?:\s|,|\.|$)`),
	// French: "Dupont Automobiles SAS"
	regexp.MustCompile(`[A-ZÀ-Ö][a-zà-ö]{2,20}(?:\s+[A-ZÀ-Ö][a-zà-ö]{2,20}){0,2}\s+Automobiles?\s+(?:SAS|SARL|SA|SNC)`),
	// Spanish: "Concesionario García SL"
	regexp.MustCompile(`(?i)(?:Concesionario|Concesión|Talleres?|Automóviles?)\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]{2,}[\w\s\-]{0,40}?(?:\s+(?:SL|SLU|SA|SLL))?(?:\s|,|\.|$)`),
	// Dutch: "Autobedrijf de Jong BV"
	regexp.MustCompile(`(?i)(?:Autobedrijf|Autohandel)\s+[A-Z][a-z]{2,}[\w\s\-]{0,40}?(?:\s+(?:BV|NV|VOF|CV))?(?:\s|,|\.|$)`),
	// Generic: "Mueller Motors" / "Renault Autohaus Berlin"
	regexp.MustCompile(`\b([A-ZÜÄÖ][a-züäöß]{2,20}(?:\s+[A-ZÜÄÖ][a-züäöß]{2,20}){0,2})\s+(?:Motors?|Automobiles?|Auto|Cars?)\b`),
}

// legalSuffixes are stripped during normalization.
var legalSuffixes = []string{
	" gmbh & co. kg", " gmbh & co kg", " gmbh", " ag", " kg", " ohg",
	" e.k.", " e.v.", " gbr",
	" sas", " sarl", " sa", " snc", " srl",
	" sl", " slu", " sll",
	" bv", " nv", " vof", " cv",
}

// ExtractCandidates returns distinct dealer name candidates from text, sorted
// by first appearance. Both raw and normalized forms are returned.
func ExtractCandidates(text string) []Candidate {
	seen := map[string]bool{}
	var out []Candidate

	for _, re := range patterns {
		for _, m := range re.FindAllString(text, -1) {
			m = strings.TrimRight(strings.TrimSpace(m), " ,.")
			if len(m) < 5 || len(m) > 100 {
				continue
			}
			norm := Normalize(m)
			if norm == "" || len(norm) < 4 || seen[norm] {
				continue
			}
			seen[norm] = true
			out = append(out, Candidate{Raw: m, Normalized: norm})
		}
	}
	return out
}

// Normalize produces a lowercase, suffix-stripped, letter-only form of a dealer
// name suitable for equality comparison against normalized_name in dealer_entity.
func Normalize(name string) string {
	lower := strings.ToLower(strings.TrimSpace(name))
	for _, sfx := range legalSuffixes {
		if strings.HasSuffix(lower, sfx) {
			lower = strings.TrimSuffix(lower, sfx)
			break
		}
	}
	// Strip leading context words (autohaus, garage, etc.)
	for _, prefix := range []string{"autohaus ", "garage ", "concesionario ", "autobedrijf ", "talleres ", "automobiles "} {
		if strings.HasPrefix(lower, prefix) {
			lower = strings.TrimPrefix(lower, prefix)
			break
		}
	}
	// Keep only letters, spaces, hyphens.
	var b strings.Builder
	for _, r := range lower {
		if unicode.IsLetter(r) || r == ' ' || r == '-' {
			b.WriteRune(r)
		}
	}
	return strings.TrimSpace(b.String())
}
