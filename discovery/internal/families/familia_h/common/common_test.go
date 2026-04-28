package common_test

import (
	"testing"

	"cardex.eu/discovery/internal/families/familia_h/common"
)

// ── ParseResponse ─────────────────────────────────────────────────────────────

func TestParseResponse_DealersEnvelope(t *testing.T) {
	body := []byte(`{"dealers":[
		{"id":"D1","name":"Dealer One","address":{"postalCode":"10115","city":"Berlin","countryCode":"DE"}},
		{"dealerId":"D2","name":"Dealer Two","address":{"zipCode":"20095","city":"Hamburg","countryCode":"DE"}}
	]}`)
	dealers, err := common.ParseResponse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(dealers) != 2 {
		t.Fatalf("want 2, got %d", len(dealers))
	}
	if dealers[0].CanonicalID() != "D1" {
		t.Errorf("dealers[0].ID = %q, want D1", dealers[0].CanonicalID())
	}
	if dealers[1].CanonicalID() != "D2" {
		t.Errorf("dealers[1].DealerID = %q, want D2", dealers[1].CanonicalID())
	}
}

func TestParseResponse_DealershipsEnvelope(t *testing.T) {
	body := []byte(`{"dealerships":[{"id":"M1","name":"MB Berlin","address":{"postalCode":"10117","city":"Berlin","countryCode":"DE"}}]}`)
	dealers, err := common.ParseResponse(body)
	if err != nil || len(dealers) != 1 {
		t.Fatalf("err=%v, len=%d", err, len(dealers))
	}
}

func TestParseResponse_AlternativeEnvelopes(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{"results", `{"results":[{"id":"R1","name":"R Dealer","address":{"countryCode":"FR"}}]}`},
		{"data", `{"data":[{"id":"D1","name":"D Dealer","address":{"countryCode":"NL"}}]}`},
		{"items", `{"items":[{"id":"I1","name":"I Dealer","address":{"countryCode":"BE"}}]}`},
		{"locations", `{"locations":[{"id":"L1","name":"L Dealer","address":{"countryCode":"CH"}}]}`},
		{"points", `{"points":[{"id":"P1","name":"P Dealer","address":{"countryCode":"ES"}}]}`},
		{"array", `[{"id":"A1","name":"A Dealer","address":{"countryCode":"DE"}}]`},
	}
	for _, tc := range cases {
		dealers, err := common.ParseResponse([]byte(tc.body))
		if err != nil {
			t.Errorf("%s: unexpected error: %v", tc.name, err)
			continue
		}
		if len(dealers) != 1 {
			t.Errorf("%s: want 1, got %d", tc.name, len(dealers))
		}
	}
}

func TestParseResponse_ExtraKeys(t *testing.T) {
	// Nested key not in the standard envelope list
	body := []byte(`{"garages":[{"id":"G1","name":"Garage Un","address":{"countryCode":"FR"}}]}`)
	dealers, err := common.ParseResponse(body, "garages")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(dealers) != 1 {
		t.Fatalf("want 1, got %d", len(dealers))
	}
	if dealers[0].CanonicalID() != "G1" {
		t.Errorf("ID = %q, want G1", dealers[0].CanonicalID())
	}
}

func TestParseResponse_Empty(t *testing.T) {
	dealers, err := common.ParseResponse(nil)
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if len(dealers) != 0 {
		t.Errorf("expected empty, got %v", dealers)
	}
}

// ── GenericDealer canonical methods ──────────────────────────────────────────

func TestGenericDealer_CanonicalID_Priority(t *testing.T) {
	d := common.GenericDealer{}
	d.DealerCode = "code-1"
	d.ID = "id-1"
	// ID has highest priority
	if d.CanonicalID() != "id-1" {
		t.Errorf("expected id-1, got %q", d.CanonicalID())
	}
}

func TestGenericDealer_CanonicalID_Fallbacks(t *testing.T) {
	d := common.GenericDealer{}
	if d.CanonicalID() != "" {
		t.Errorf("empty dealer should return empty ID")
	}
	d.SiteID = "site-5"
	if d.CanonicalID() != "site-5" {
		t.Errorf("expected site-5, got %q", d.CanonicalID())
	}
}

func TestGenericDealer_PostalCode_Variants(t *testing.T) {
	d := common.GenericDealer{}
	d.Address.ZipCode = "75001"
	if d.PostalCode() != "75001" {
		t.Errorf("expected 75001, got %q", d.PostalCode())
	}
	d.Address.PostalCode = "75002"
	if d.PostalCode() != "75002" {
		t.Errorf("postalCode should win over zipCode, got %q", d.PostalCode())
	}
}

func TestGenericDealer_CountryCode_Variants(t *testing.T) {
	d := common.GenericDealer{}
	d.Address.Country = "DE"
	if d.CountryCode() != "DE" {
		t.Errorf("expected DE, got %q", d.CountryCode())
	}
	d.Address.CountryCode = "FR"
	if d.CountryCode() != "FR" {
		t.Errorf("countryCode should win over country, got %q", d.CountryCode())
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func TestExtractDomain(t *testing.T) {
	cases := []struct{ in, want string }{
		{"https://www.bmw.de/dealer-locator", "bmw.de"},
		{"https://mercedes-benz.fr/concessionnaire", "mercedes-benz.fr"},
		{"http://example.com/path", "example.com"},
		{"not-a-url", "not-a-url"},
		{"", ""},
	}
	for _, c := range cases {
		got := common.ExtractDomain(c.in)
		if got != c.want {
			t.Errorf("ExtractDomain(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestPtrIfNotEmpty(t *testing.T) {
	if common.PtrIfNotEmpty("") != nil {
		t.Error("empty string should return nil")
	}
	p := common.PtrIfNotEmpty("hello")
	if p == nil || *p != "hello" {
		t.Error("non-empty string should return pointer")
	}
}
