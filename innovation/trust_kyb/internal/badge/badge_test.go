package badge_test

import (
	"bytes"
	"strings"
	"testing"

	"cardex.eu/trust/internal/badge"
)

func TestGenerateAllTiers(t *testing.T) {
	tiers := []string{"platinum", "gold", "silver", "unverified"}
	for _, tier := range tiers {
		svg, err := badge.Generate(tier)
		if err != nil {
			t.Fatalf("tier %q: Generate() error: %v", tier, err)
		}
		if len(svg) == 0 {
			t.Fatalf("tier %q: empty SVG output", tier)
		}
		if !bytes.HasPrefix(svg, []byte("<svg")) {
			t.Errorf("tier %q: output does not start with <svg>", tier)
		}
		if !bytes.Contains(svg, []byte("</svg>")) {
			t.Errorf("tier %q: output missing closing </svg>", tier)
		}
	}
}

func TestTierLabelInSVG(t *testing.T) {
	cases := []struct {
		tier  string
		label string
	}{
		{"platinum", "PLATINUM"},
		{"gold", "GOLD"},
		{"silver", "SILVER"},
		{"unverified", "UNVERIFIED"},
	}
	for _, c := range cases {
		svg, err := badge.Generate(c.tier)
		if err != nil {
			t.Fatalf("tier %q: Generate() error: %v", c.tier, err)
		}
		if !strings.Contains(string(svg), c.label) {
			t.Errorf("tier %q: SVG missing label %q", c.tier, c.label)
		}
	}
}

func TestUnknownTierFallsBackToUnverified(t *testing.T) {
	svg, err := badge.Generate("does-not-exist")
	if err != nil {
		t.Fatalf("unknown tier should not error: %v", err)
	}
	if !strings.Contains(string(svg), "UNVERIFIED") {
		t.Error("unknown tier should render as UNVERIFIED")
	}
}

func TestSVGIsDeterministic(t *testing.T) {
	s1, _ := badge.Generate("gold")
	s2, _ := badge.Generate("gold")
	if !bytes.Equal(s1, s2) {
		t.Error("badge output should be deterministic for the same tier")
	}
}

func TestContentType(t *testing.T) {
	ct := badge.ContentType()
	if !strings.HasPrefix(ct, "image/svg+xml") {
		t.Errorf("unexpected content type: %q", ct)
	}
}

func TestPlatinumUsesGoldColor(t *testing.T) {
	svg, _ := badge.Generate("platinum")
	if !strings.Contains(string(svg), "#FFD700") {
		t.Error("platinum badge should contain gold colour #FFD700")
	}
}
