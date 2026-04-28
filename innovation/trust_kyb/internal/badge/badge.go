// Package badge generates embeddable SVG trust-tier badges.
// Badges are 180×36 px, cacheable, and designed for inline use on dealer websites.
package badge

import (
	"bytes"
	"fmt"
	"text/template"
)

type tierStyle struct {
	BgColor     string
	TextColor   string
	BorderColor string
	TierLabel   string
	ScoreStr    string
}

// svgTemplate renders a shield-style two-panel SVG badge.
// Left panel: "CARDEX TRUST" branding; right panel: tier in tier colour.
const svgTemplate = `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="36">
  <defs>
    <linearGradient id="bg-l" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a1a2e"/>
      <stop offset="100%" stop-color="#0d1117"/>
    </linearGradient>
  </defs>
  <!-- left panel -->
  <rect x="0" y="0" width="90" height="36" rx="4" ry="4" fill="url(#bg-l)"/>
  <!-- right panel -->
  <rect x="90" y="0" width="90" height="36" rx="4" ry="4" fill="{{.BgColor}}"/>
  <!-- border -->
  <rect x="0.5" y="0.5" width="179" height="35" rx="3.5" ry="3.5"
        fill="none" stroke="{{.BorderColor}}" stroke-width="1"/>
  <!-- divider -->
  <line x1="90" y1="4" x2="90" y2="32" stroke="{{.BorderColor}}" stroke-width="0.5" stroke-opacity="0.4"/>
  <!-- left text: CARDEX TRUST -->
  <text x="45" y="16" font-family="DejaVu Sans,Arial,sans-serif" font-size="9"
        fill="#aaaaaa" text-anchor="middle">CARDEX</text>
  <text x="45" y="28" font-family="DejaVu Sans,Arial,sans-serif" font-size="9"
        fill="#ffffff" text-anchor="middle" font-weight="bold">TRUST</text>
  <!-- right text: tier -->
  <text x="135" y="22" font-family="DejaVu Sans,Arial,sans-serif" font-size="11"
        fill="{{.TextColor}}" text-anchor="middle" font-weight="bold">{{.TierLabel}}</text>
</svg>`

var tmpl = template.Must(template.New("badge").Parse(svgTemplate))

var tierStyles = map[string]tierStyle{
	"platinum":   {BgColor: "#0d1b00", TextColor: "#FFD700", BorderColor: "#FFD700", TierLabel: "PLATINUM"},
	"gold":       {BgColor: "#0d0d1a", TextColor: "#C0C0C0", BorderColor: "#A8A8A8", TierLabel: "GOLD"},
	"silver":     {BgColor: "#1a0d00", TextColor: "#CD7F32", BorderColor: "#A0522D", TierLabel: "SILVER"},
	"unverified": {BgColor: "#1a1a1a", TextColor: "#9E9E9E", BorderColor: "#666666", TierLabel: "UNVERIFIED"},
}

// Generate returns an SVG badge byte slice for the given trust tier.
// Unknown tiers fall back to "unverified" styling.
func Generate(tier string) ([]byte, error) {
	st, ok := tierStyles[tier]
	if !ok {
		st = tierStyles["unverified"]
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, st); err != nil {
		return nil, fmt.Errorf("badge: render %q: %w", tier, err)
	}
	return buf.Bytes(), nil
}

// ContentType returns the MIME type for SVG badges.
func ContentType() string { return "image/svg+xml; charset=utf-8" }
