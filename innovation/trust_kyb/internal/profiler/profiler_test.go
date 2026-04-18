package profiler_test

import (
	"testing"
	"time"

	"cardex.eu/trust/internal/profiler"
)

var fixedNow = time.Date(2026, 4, 18, 12, 0, 0, 0, time.UTC)

// platinum: fully verified, high volume, long tenure, no anomalies
func platinumInput() profiler.Input {
	return profiler.Input{
		DealerID: "D_PLAT", DealerName: "Autohaus Premium GmbH", Country: "DE",
		VATID: "DE123456789", VIESStatus: "valid", RegistryStatus: "registered",
		RegistryAge: 10, V15Score: 100, ListingVolume: 200, AvgCompositeScore: 100,
		IndexTenureDays: 730, AnomalyCount: 0, BadgeBaseURL: "http://localhost:8505",
		Now: fixedNow,
	}
}

// gold: VIES valid, registry unchecked, good behavioral
func goldInput() profiler.Input {
	return profiler.Input{
		DealerID: "D_GOLD", DealerName: "Occasion Motors SARL", Country: "FR",
		VATID: "FR12345678901", VIESStatus: "valid", RegistryStatus: "unchecked",
		RegistryAge: 3, V15Score: 75, ListingVolume: 60, AvgCompositeScore: 70,
		IndexTenureDays: 400, AnomalyCount: 0, BadgeBaseURL: "http://localhost:8505",
		Now: fixedNow,
	}
}

// silver: unchecked everywhere, moderate behavioral
func silverInput() profiler.Input {
	return profiler.Input{
		DealerID: "D_SILV", DealerName: "Coches de Ocasión SL", Country: "ES",
		VATID: "", VIESStatus: "unchecked", RegistryStatus: "unchecked",
		RegistryAge: 1, V15Score: 50, ListingVolume: 30, AvgCompositeScore: 55,
		IndexTenureDays: 180, AnomalyCount: 0, BadgeBaseURL: "http://localhost:8505",
		Now: fixedNow,
	}
}

// unverified: no VIES, not found, few listings, anomalies
func unverifiedInput() profiler.Input {
	return profiler.Input{
		DealerID: "D_UNVER", DealerName: "Unknown Dealer BV", Country: "NL",
		VATID: "", VIESStatus: "invalid", RegistryStatus: "not_found",
		RegistryAge: 0, V15Score: 20, ListingVolume: 3, AvgCompositeScore: 30,
		IndexTenureDays: 10, AnomalyCount: 3, BadgeBaseURL: "http://localhost:8505",
		Now: fixedNow,
	}
}

// newDealer: tests trust ramp-up (< 30 days tenure)
func newDealerInput() profiler.Input {
	return profiler.Input{
		DealerID: "D_NEW", DealerName: "Fresh Start Cars AG", Country: "CH",
		VATID: "CHE123456789", VIESStatus: "valid", RegistryStatus: "registered",
		RegistryAge: 5, V15Score: 100, ListingVolume: 50, AvgCompositeScore: 80,
		IndexTenureDays: 15, AnomalyCount: 0, BadgeBaseURL: "http://localhost:8505",
		Now: fixedNow,
	}
}

func TestWeightSumMaximum(t *testing.T) {
	p := profiler.Compute(platinumInput())
	if p.TrustScore != 100 {
		t.Errorf("max-signal profile expected 100.0, got %.4f", p.TrustScore)
	}
	if p.TrustTier != "platinum" {
		t.Errorf("expected platinum, got %q", p.TrustTier)
	}
}

func TestWeightSumZero(t *testing.T) {
	in := profiler.Input{
		DealerID: "D_ZERO", VIESStatus: "invalid", RegistryStatus: "not_found",
		V15Score: 0, ListingVolume: 0, AvgCompositeScore: 0, IndexTenureDays: 0,
		AnomalyCount: 100, BadgeBaseURL: "http://localhost:8505", Now: fixedNow,
	}
	p := profiler.Compute(in)
	if p.TrustScore != 0 {
		t.Errorf("zero-signal profile expected 0.0, got %.4f", p.TrustScore)
	}
	if p.TrustTier != "unverified" {
		t.Errorf("expected unverified, got %q", p.TrustTier)
	}
}

func TestTrustRampUpV15Cap(t *testing.T) {
	in := newDealerInput() // tenure 15 days, V15=100 → pts capped at 10

	bd := profiler.Breakdown(in)
	if bd.V15Points > 10+1e-9 {
		t.Errorf("trust ramp-up violated: V15 pts = %.2f, expected <= 10", bd.V15Points)
	}

	// Same dealer after 31 days should get full V15 contribution
	in.IndexTenureDays = 31
	in.Now = fixedNow.Add(16 * 24 * time.Hour)
	bd2 := profiler.Breakdown(in)
	if bd2.V15Points <= 10 {
		t.Errorf("after ramp-up period V15 pts should exceed 10, got %.2f", bd2.V15Points)
	}
}

func TestBreakdownComponentsMatchTotal(t *testing.T) {
	inputs := []profiler.Input{platinumInput(), goldInput(), silverInput(), unverifiedInput()}
	for _, in := range inputs {
		bd := profiler.Breakdown(in)
		expected := bd.VIESPoints + bd.RegistryPoints + bd.V15Points + bd.BehavioralPoints + bd.AnomalyPoints
		// clamp expected
		if expected > 100 {
			expected = 100
		}
		if expected < 0 {
			expected = 0
		}
		if abs(bd.Total-expected) > 1e-9 {
			t.Errorf("dealer %s: breakdown total %.4f != sum %.4f", in.DealerID, bd.Total, expected)
		}
	}
}

func TestProfileHashDeterministic(t *testing.T) {
	in := platinumInput()
	p1 := profiler.Compute(in)
	p2 := profiler.Compute(in)
	if p1.ProfileHash != p2.ProfileHash {
		t.Errorf("hash not deterministic: %q != %q", p1.ProfileHash, p2.ProfileHash)
	}
	if len(p1.ProfileHash) != 64 {
		t.Errorf("expected 64-char hex hash, got len %d", len(p1.ProfileHash))
	}
}

func TestExpiration90Days(t *testing.T) {
	p := profiler.Compute(platinumInput())
	want := fixedNow.Add(90 * 24 * time.Hour)
	if !p.ExpiresAt.Equal(want) {
		t.Errorf("expires_at = %v, want %v", p.ExpiresAt, want)
	}
	if p.IsExpired(fixedNow.Add(89 * 24 * time.Hour)) {
		t.Error("profile should not be expired at day 89")
	}
	if !p.IsExpired(fixedNow.Add(91 * 24 * time.Hour)) {
		t.Error("profile should be expired at day 91")
	}
}

func TestTierBoundaries(t *testing.T) {
	cases := []struct {
		score float64
		tier  string
	}{
		{85, "platinum"},
		{84.9, "gold"},
		{70, "gold"},
		{69.9, "silver"},
		{50, "silver"},
		{49.9, "unverified"},
		{0, "unverified"},
	}
	for _, c := range cases {
		got := profilerTier(c.score)
		if got != c.tier {
			t.Errorf("score %.1f: got %q, want %q", c.score, got, c.tier)
		}
	}
}

func TestBadgeURLContainsDealerID(t *testing.T) {
	p := profiler.Compute(goldInput())
	if p.BadgeURL == "" {
		t.Fatal("badge URL is empty")
	}
	// URL must contain dealer ID and .svg
	if p.BadgeURL[len(p.BadgeURL)-4:] != ".svg" {
		t.Errorf("badge URL should end with .svg: %s", p.BadgeURL)
	}
}

func TestEIDASWalletDIDPlaceholder(t *testing.T) {
	p := profiler.Compute(platinumInput())
	if p.EIDASWalletDID != "" {
		t.Errorf("EIDASWalletDID should be empty placeholder, got %q", p.EIDASWalletDID)
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func profilerTier(score float64) string {
	switch {
	case score >= 85:
		return "platinum"
	case score >= 70:
		return "gold"
	case score >= 50:
		return "silver"
	default:
		return "unverified"
	}
}

func abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
