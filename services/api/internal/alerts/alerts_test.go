package alerts

import (
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/api/internal/arbitrage"
	"cardex.eu/api/internal/store"
)

func newTestHandler() *Handler {
	return NewHandler(nil, nil, slog.New(slog.DiscardHandler))
}

func req() *http.Request {
	return httptest.NewRequest(http.MethodPost, "/api/v1/alerts", nil)
}

func TestValidateRequiresMakeModel(t *testing.T) {
	h := newTestHandler()
	if _, err := h.validate(CreateRequest{Model: "320d", WebhookURL: "https://x.io/h"}, req()); err == nil {
		t.Error("expected error when make missing")
	}
	if _, err := h.validate(CreateRequest{Make: "BMW", WebhookURL: "https://x.io/h"}, req()); err == nil {
		t.Error("expected error when model missing")
	}
}

func TestValidateRequiresChannel(t *testing.T) {
	h := newTestHandler()
	if _, err := h.validate(CreateRequest{Make: "BMW", Model: "320d"}, req()); err == nil {
		t.Error("expected error when no webhook or email")
	}
}

func TestValidateWebhookURL(t *testing.T) {
	h := newTestHandler()
	if _, err := h.validate(CreateRequest{Make: "BMW", Model: "320d", WebhookURL: "not-a-url"}, req()); err == nil {
		t.Error("expected error for invalid webhook URL")
	}
	if _, err := h.validate(CreateRequest{Make: "BMW", Model: "320d", WebhookURL: "ftp://x/y"}, req()); err == nil {
		t.Error("expected error for non-http webhook URL")
	}
}

func TestValidateCountriesAndDefaults(t *testing.T) {
	h := newTestHandler()
	a, err := h.validate(CreateRequest{
		Make: "BMW", Model: "320d", Email: "dealer@example.com",
		BuyCountries: []string{"de", "fr"}, SellCountries: []string{"es"},
	}, req())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if a.MinMarginPct != 5 {
		t.Errorf("default margin = %v, want 5", a.MinMarginPct)
	}
	if a.BuyCountries[0] != "DE" || a.BuyCountries[1] != "FR" {
		t.Errorf("buy countries not upper-cased: %v", a.BuyCountries)
	}
	if a.ID == "" || a.Active != true {
		t.Errorf("alert id/active not set: id=%q active=%v", a.ID, a.Active)
	}

	if _, err := h.validate(CreateRequest{
		Make: "BMW", Model: "320d", Email: "d@e.com", BuyCountries: []string{"XX"},
	}, req()); err == nil {
		t.Error("expected error for unsupported country")
	}
}

func TestValidateRejectsHeaderInjection(t *testing.T) {
	h := newTestHandler()
	// CRLF in make → header injection vector for the email subject.
	if _, err := h.validate(CreateRequest{
		Make: "BMW\r\nBcc: evil@x.com", Model: "320d", Email: "d@e.com",
	}, req()); err == nil {
		t.Error("expected error for CRLF in make")
	}
	// CRLF in email → recipient header injection.
	if _, err := h.validate(CreateRequest{
		Make: "BMW", Model: "320d", Email: "d@e.com\r\nBcc: evil@x.com",
	}, req()); err == nil {
		t.Error("expected error for CRLF in email")
	}
}

func TestValidateLengthCap(t *testing.T) {
	h := newTestHandler()
	long := strings.Repeat("A", 65)
	if _, err := h.validate(CreateRequest{Make: long, Model: "320d", Email: "d@e.com"}, req()); err == nil {
		t.Error("expected error for over-long make")
	}
}

func TestIsPublicIP(t *testing.T) {
	tests := []struct {
		ip   string
		want bool
	}{
		{"8.8.8.8", true},
		{"1.1.1.1", true},
		{"127.0.0.1", false},       // loopback
		{"10.0.0.5", false},        // RFC1918
		{"192.168.1.1", false},     // RFC1918
		{"172.16.0.1", false},      // RFC1918
		{"169.254.169.254", false}, // cloud metadata (link-local)
		{"0.0.0.0", false},         // unspecified
		{"::1", false},             // IPv6 loopback
		{"fd00::1", false},         // IPv6 ULA (private)
	}
	for _, tc := range tests {
		ip := net.ParseIP(tc.ip)
		if ip == nil {
			t.Fatalf("bad test IP %q", tc.ip)
		}
		if got := isPublicIP(ip); got != tc.want {
			t.Errorf("isPublicIP(%s) = %v, want %v", tc.ip, got, tc.want)
		}
	}
}

func TestSignatureIsOrderIndependent(t *testing.T) {
	a := []arbitrage.Opportunity{
		{BuyCountry: "DE", SellCountry: "ES", Listing: store.Listing{ID: "v1"}, NetMarginEUR: 1000},
		{BuyCountry: "FR", SellCountry: "NL", Listing: store.Listing{ID: "v2"}, NetMarginEUR: 2000},
	}
	b := []arbitrage.Opportunity{a[1], a[0]} // reversed order
	if signature(a) != signature(b) {
		t.Error("signature should be order-independent")
	}

	c := []arbitrage.Opportunity{
		{BuyCountry: "DE", SellCountry: "ES", Listing: store.Listing{ID: "v1"}, NetMarginEUR: 1500}, // changed margin
		a[1],
	}
	if signature(a) == signature(c) {
		t.Error("signature should change when an opportunity changes")
	}
}
