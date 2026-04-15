package dms_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/discovery/internal/families/familia_d/dms"
)

// fixedHostTransport rewrites all requests to a fixed test server.
type fixedHostTransport struct{ target string }

func (t *fixedHostTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	clone.URL.Scheme = "http"
	clone.URL.Host = strings.TrimPrefix(t.target, "http://")
	return http.DefaultTransport.RoundTrip(clone)
}

func TestDetectDMS_HTMLBody_DealerConnect(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`<html><head>
<script src="https://cdn.dealerconnect.de/assets/v2/main.js"></script>
</head><body>Autohaus Muster</body></html>`))
	}))
	defer srv.Close()

	d := dms.NewWithClient(&http.Client{
		Transport: &fixedHostTransport{target: srv.URL},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	})
	result, err := d.DetectDMS(context.Background(), "autohaus-muster.de")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Detected {
		t.Fatal("want DMS detected")
	}
	if result.Provider != dms.ProviderDealerConnect {
		t.Errorf("Provider = %q, want dealerconnect.de", result.Provider)
	}
	if result.Method != "html_template" {
		t.Errorf("Method = %q, want html_template", result.Method)
	}
}

func TestDetectDMS_HTMLBody_MotorMarket(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`<html><head>
<link rel="stylesheet" href="https://assets.motormarket.de/styles/main.css"/>
</head><body>Autohaus</body></html>`))
	}))
	defer srv.Close()

	d := dms.NewWithClient(&http.Client{
		Transport: &fixedHostTransport{target: srv.URL},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	})
	result, err := d.DetectDMS(context.Background(), "garage.de")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Detected || result.Provider != dms.ProviderMotorMarket {
		t.Errorf("want motormarket.de detected, got detected=%v provider=%q",
			result.Detected, result.Provider)
	}
}

func TestDetectDMS_NoDMS(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("<html><body>Custom dealer website</body></html>"))
	}))
	defer srv.Close()

	d := dms.NewWithClient(&http.Client{
		Transport: &fixedHostTransport{target: srv.URL},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	})
	result, err := d.DetectDMS(context.Background(), "unique-dealer.de")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Detected {
		t.Errorf("want Detected=false, got provider=%q", result.Provider)
	}
}

func TestDetectDMS_FlotaNet_Body(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`<html><body>
<script>window.__FLOTA_CONFIG__ = {"provider":"flota.net","version":"3.2"};</script>
</body></html>`))
	}))
	defer srv.Close()

	d := dms.NewWithClient(&http.Client{
		Transport: &fixedHostTransport{target: srv.URL},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	})
	result, err := d.DetectDMS(context.Background(), "concesionario.es")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Detected || result.Provider != dms.ProviderFlotaNet {
		t.Errorf("want flota.net detected, got detected=%v provider=%q",
			result.Detected, result.Provider)
	}
}
