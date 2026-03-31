package ahocorasick

import "testing"

func TestScanner_Scan(t *testing.T) {
	scanner := New()

	tests := []struct {
		name       string
		text       string
		wantMatch  bool
		wantKeyword string
	}{
		{
			name:       "German margin scheme",
			text:       "Fahrzeug nach §25a UStG",
			wantMatch:  true,
			wantKeyword: "§25a",
		},
		{
			name:       "Dutch margin",
			text:       "Auto verkocht onder margeregeling",
			wantMatch:  true,
			wantKeyword: "margeregeling",
		},
		{
			name:       "Italian margin",
			text:       "Vendita regime del margine IVA",
			wantMatch:  true,
			wantKeyword: "regime del margine",
		},
		{
			name:       "no match clean listing",
			text:       "BMW 330i 2024 Diesel Automatik",
			wantMatch:  false,
			wantKeyword: "",
		},
		{
			name:       "case insensitive",
			text:       "DIFFERENZBESTEUERUNG GILT",
			wantMatch:  true,
			wantKeyword: "differenzbesteuerung",
		},
		{
			name:       "marge substring",
			text:       "Vendu en marge de la TVA",
			wantMatch:  true,
			wantKeyword: "marge",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			matched, keyword := scanner.Scan(tt.text)
			if matched != tt.wantMatch {
				t.Errorf("Scan() matched = %v, want %v", matched, tt.wantMatch)
			}
			if keyword != tt.wantKeyword {
				t.Errorf("Scan() keyword = %q, want %q", keyword, tt.wantKeyword)
			}
		})
	}
}
