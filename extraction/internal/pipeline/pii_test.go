package pipeline

import "testing"

func TestSanitizePIIString_Email(t *testing.T) {
	cases := []struct {
		in      string
		wantHit bool
	}{
		{"Contact john.doe@example.com for details", true},
		{"vendeur@concession-paris.fr", true},
		{"info@autohaus-berlin.de", true},
		{"No contact info here", false},
		{"VIN: WVW123456789", false},
	}
	for _, tc := range cases {
		_, changed := sanitizePIIString(tc.in)
		if changed != tc.wantHit {
			t.Errorf("email: sanitizePIIString(%q) changed=%v want=%v", tc.in, changed, tc.wantHit)
		}
	}
}

func TestSanitizePIIString_Phone(t *testing.T) {
	cases := []struct {
		in      string
		wantHit bool
	}{
		{"Appeler au +33 1 23 45 67 89", true},
		{"Tel: +34 91 234 56 78", true},
		{"No phone here, just text", false},
		{"VIN: WVW123456789", false},    // VIN — no separators between groups
		{"Puissance: 150 kW", false},    // engine power
		{"Année: 2021", false},          // year
	}
	for _, tc := range cases {
		_, changed := sanitizePIIString(tc.in)
		if changed != tc.wantHit {
			t.Errorf("phone: sanitizePIIString(%q) changed=%v want=%v", tc.in, changed, tc.wantHit)
		}
	}
}

func TestSanitizePIIString_PersonName(t *testing.T) {
	cases := []struct {
		in      string
		wantHit bool
	}{
		{"Contact: Jean Dupont", true},
		{"Vendeur: María García", true},
		{"Verkäufer: Klaus Müller", true},
		{"Ansprechpartner: Hans Schmidt", true},
		{"Farbe: Schwarz Metallic", false},
		{"Modell: Golf Variant", false},
	}
	for _, tc := range cases {
		_, changed := sanitizePIIString(tc.in)
		if changed != tc.wantHit {
			t.Errorf("name: sanitizePIIString(%q) changed=%v want=%v", tc.in, changed, tc.wantHit)
		}
	}
}

func TestSanitizeVehicle_WithPII(t *testing.T) {
	v := &VehicleRaw{
		AdditionalFields: map[string]interface{}{
			"description": "Contactez Jean Dupont à vendeur@dealer.fr ou au +33 6 12 34 56 78",
			"disclaimer":  "Prix négociable",
			"power_raw":   150, // int — must be untouched
		},
	}

	n := SanitizeVehicle(v)
	if n == 0 {
		t.Fatal("SanitizeVehicle: expected at least 1 field modified")
	}
	desc, _ := v.AdditionalFields["description"].(string)
	if desc == "Contactez Jean Dupont à vendeur@dealer.fr ou au +33 6 12 34 56 78" {
		t.Error("description field was not sanitized")
	}
	if v.AdditionalFields["power_raw"] != 150 {
		t.Error("non-string field was modified — must be untouched")
	}
	if v.AdditionalFields["disclaimer"] != "Prix négociable" {
		t.Error("clean string field was unexpectedly modified")
	}
}

func TestSanitizeVehicle_NilSafe(t *testing.T) {
	if n := SanitizeVehicle(nil); n != 0 {
		t.Errorf("SanitizeVehicle(nil) = %d, want 0", n)
	}
}

func TestSanitizeVehicles_Multiple(t *testing.T) {
	vehicles := []*VehicleRaw{
		{AdditionalFields: map[string]interface{}{"note": "Contact: Hans Schmidt"}},
		{AdditionalFields: map[string]interface{}{"note": "Voir avec le dealer"}},
		{AdditionalFields: map[string]interface{}{"email": "info@garage.fr"}},
	}
	n := SanitizeVehicles(vehicles)
	if n < 2 {
		t.Errorf("SanitizeVehicles: got %d modifications, want >= 2", n)
	}
}

func TestTruncateVINForLog(t *testing.T) {
	cases := []struct{ in, want string }{
		{"WVW ZZZ1JZ3W000001", "WVW ZZZ1JZ3W00****"}, // 18 chars, last 4 masked
		{"1HGBH41JXMN109186", "1HGBH41JXMN10****"},   // 17 chars, last 4 masked
		{"AB12", "****"},
		{"XY", "**"},
	}
	for _, tc := range cases {
		got := TruncateVINForLog(tc.in)
		if got != tc.want {
			t.Errorf("TruncateVINForLog(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}
