package plugins_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/discovery/internal/families/familia_d/plugins"
)

// routedTransport redirects all requests to the given test server.
type routedTransport struct{ target string }

func (t *routedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	clone.URL.Scheme = "http"
	clone.URL.Host = strings.TrimPrefix(t.target, "http://")
	return http.DefaultTransport.RoundTrip(clone)
}

func TestDetectPlugins_WordPress_VehicleCPT(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/wp-json/wp/v2/vehicles":
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`[{"id":1,"title":"BMW 320d"}]`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	d := plugins.NewWithClient(&http.Client{Transport: &routedTransport{target: srv.URL}})
	result, err := d.DetectPlugins(context.Background(), "garage.de", "wordpress")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Plugins) == 0 {
		t.Fatal("want at least 1 plugin detected, got 0")
	}
	found := false
	for _, p := range result.Plugins {
		if p == "vehicle-cpt" {
			found = true
		}
	}
	if !found {
		t.Errorf("plugin 'vehicle-cpt' not in %v", result.Plugins)
	}
	if len(result.Endpoints) == 0 {
		t.Error("want at least 1 extraction endpoint")
	}
}

func TestDetectPlugins_WordPress_NoPlugins(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	d := plugins.NewWithClient(&http.Client{Transport: &routedTransport{target: srv.URL}})
	result, err := d.DetectPlugins(context.Background(), "plain-site.de", "wordpress")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Plugins) != 0 {
		t.Errorf("want 0 plugins, got %v", result.Plugins)
	}
}

func TestDetectPlugins_Joomla_ComCarmanager(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("option")
		if q == "com_carmanager" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"items":[]}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	d := plugins.NewWithClient(&http.Client{Transport: &routedTransport{target: srv.URL}})
	result, err := d.DetectPlugins(context.Background(), "dealer.es", "joomla")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	found := false
	for _, p := range result.Plugins {
		if p == "com_carmanager" {
			found = true
		}
	}
	if !found {
		t.Errorf("com_carmanager not detected, got %v", result.Plugins)
	}
}

func TestDetectPlugins_UnsupportedCMS(t *testing.T) {
	d := plugins.New()
	result, err := d.DetectPlugins(context.Background(), "example.com", "wix")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Plugins) != 0 {
		t.Errorf("want 0 plugins for unsupported CMS, got %v", result.Plugins)
	}
}
