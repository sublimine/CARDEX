package kg

// BaseWeights maps each family ID to its contribution weight.
// Sprint 1 — only Family A is wired. Additional families are registered here
// as they are implemented.
// Full formula (TODO Sprint 3): Bayesian combination with source independence
// adjustment.  Current implementation: plain sum, clamped to [0.0, 1.0].
var BaseWeights = map[string]float64{
	"A": 0.35, // Registros mercantiles — legal-fiscal, high reliability
	"B": 0.15, // Geocartografía (OSM + Wikidata) — geo-recon, medium reliability
	"C": 0.10, // Cartografía web (Wayback + CT logs + passive DNS) — web-recon, low-medium reliability
	"F": 0.20, // Aggregator dealer directories (mobile.de, AutoScout24, etc.) — marketplace-verified, high reliability
	"G": 0.20, // Sectoral associations (BOVAG, ZDK, Mobilians, etc.) — legal-commercial, high reliability
	"H": 0.25, // OEM dealer networks — OEM official = maximum authority, highest reliability
	"I": 0.05, // Inspection & certification networks — adjacent signal, low primary weight
	"K": 0.05, // Alternative search engines (SearXNG/Marginalia) — low primary, confirmation signal
	"M": 0.00, // Fiscal signal enrichment (VIES/UID) — enrichment only, uses consistency_multiplier
	// D–E, J, L, N–O: registered when implemented
}

// ComputeConfidence computes the confidence score for a dealer given the set of
// family IDs that have independently confirmed it.
//
// Current formula: sum of base weights for each distinct confirming family,
// clamped to 1.0. This is the Sprint 1 approximation; Sprint 3 will replace
// it with a proper Bayesian combination that accounts for source dependency.
func ComputeConfidence(confirmedByFamilies []string) float64 {
	seen := make(map[string]bool, len(confirmedByFamilies))
	var score float64
	for _, fam := range confirmedByFamilies {
		if seen[fam] {
			continue
		}
		seen[fam] = true
		if w, ok := BaseWeights[fam]; ok {
			score += w
		}
	}
	if score > 1.0 {
		return 1.0
	}
	return score
}
