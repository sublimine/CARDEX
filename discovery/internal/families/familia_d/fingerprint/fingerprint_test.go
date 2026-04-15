package fingerprint_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cardex.eu/discovery/internal/families/familia_d/fingerprint"
)

func serveHTML(t *testing.T, html string, headers map[string]string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for k, v := range headers {
			w.Header().Set(k, v)
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(html))
	}))
}

func TestFingerprintDomain_WordPress_GeneratorMeta(t *testing.T) {
	html := `<!DOCTYPE html><html><head>
<meta name="generator" content="WordPress 6.4.2" />
<link rel="https://api.w.org/" href="https://example.de/wp-json/" />
</head><body><p>Garage</p></body></html>`

	srv := serveHTML(t, html, nil)
	defer srv.Close()

	// Point fingerprinter at the test server by overriding host lookup:
	// We create a custom client that redirects all requests to the test server.
	client := &http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	}
	fp := fingerprint.NewWithClient(client)

	result, err := fp.FingerprintDomain(context.Background(), "example.de")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSWordPress {
		t.Errorf("CMS = %q, want %q", result.CMS, fingerprint.CMSWordPress)
	}
	if result.Version != "6.4.2" {
		t.Errorf("Version = %q, want 6.4.2", result.Version)
	}
	if result.Confidence < 0.5 {
		t.Errorf("Confidence = %.2f, want >= 0.5", result.Confidence)
	}
}

func TestFingerprintDomain_WordPress_Assets(t *testing.T) {
	html := `<!DOCTYPE html><html><head></head><body>
<script src="/wp-content/themes/auto/js/main.js"></script>
<link href="/wp-includes/css/dashicons.min.css" rel="stylesheet"/>
</body></html>`

	srv := serveHTML(t, html, nil)
	defer srv.Close()

	fp := fingerprint.NewWithClient(&http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	})

	result, err := fp.FingerprintDomain(context.Background(), "garage.fr")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSWordPress {
		t.Errorf("CMS = %q, want wordpress", result.CMS)
	}
}

func TestFingerprintDomain_Joomla(t *testing.T) {
	html := `<!DOCTYPE html><html><head>
<meta name="generator" content="Joomla! 4.2 - Open Source Content Management" />
</head><body></body></html>`

	srv := serveHTML(t, html, nil)
	defer srv.Close()

	fp := fingerprint.NewWithClient(&http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	})

	result, err := fp.FingerprintDomain(context.Background(), "dealer.es")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSJoomla {
		t.Errorf("CMS = %q, want joomla", result.CMS)
	}
	if result.Version != "4.2" {
		t.Errorf("Version = %q, want 4.2", result.Version)
	}
}

func TestFingerprintDomain_Wix(t *testing.T) {
	html := `<!DOCTYPE html><html><head></head><body>
<script src="https://static.wixstatic.com/services/wix-thunderbolt.min.js"></script>
</body></html>`

	srv := serveHTML(t, html, nil)
	defer srv.Close()

	fp := fingerprint.NewWithClient(&http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	})

	result, err := fp.FingerprintDomain(context.Background(), "wixsite.nl")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSWix {
		t.Errorf("CMS = %q, want wix", result.CMS)
	}
}

func TestFingerprintDomain_Drupal_XGenerator(t *testing.T) {
	html := `<!DOCTYPE html><html><head></head><body></body></html>`
	srv := serveHTML(t, html, map[string]string{"X-Generator": "Drupal 10 (https://www.drupal.org)"})
	defer srv.Close()

	fp := fingerprint.NewWithClient(&http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	})

	result, err := fp.FingerprintDomain(context.Background(), "dealer.be")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSDrupal {
		t.Errorf("CMS = %q, want drupal", result.CMS)
	}
}

func TestFingerprintDomain_Custom(t *testing.T) {
	html := `<!DOCTYPE html><html><head><title>Autohaus Muster</title></head>
<body><h1>Willkommen</h1></body></html>`

	srv := serveHTML(t, html, nil)
	defer srv.Close()

	fp := fingerprint.NewWithClient(&http.Client{
		Transport: &hostRedirectTransport{target: srv.URL},
	})

	result, err := fp.FingerprintDomain(context.Background(), "autohaus-muster.de")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.CMS != fingerprint.CMSCustom {
		t.Errorf("CMS = %q, want custom", result.CMS)
	}
}

// hostRedirectTransport rewrites every request to target, preserving path+query.
type hostRedirectTransport struct {
	target string
	base   http.RoundTripper
}

func (t *hostRedirectTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	clone.URL.Scheme = "http"
	clone.URL.Host = strings.TrimPrefix(t.target, "http://")
	if t.base == nil {
		return http.DefaultTransport.RoundTrip(clone)
	}
	return t.base.RoundTrip(clone)
}
