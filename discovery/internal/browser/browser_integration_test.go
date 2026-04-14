//go:build playwright_integration

// Integration tests for the browser package.
//
// These tests require Chromium to be installed via:
//
//	go run github.com/playwright-community/playwright-go/cmd/playwright install chromium
//
// Run with:
//
//	go test -tags playwright_integration ./internal/browser/...
package browser_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"cardex.eu/discovery/internal/browser"
)

// newTestBrowser creates a PlaywrightBrowser pointing at no specific rate-limit DB
// (nil → in-memory only) with a shortened timeout for tests.
func newTestBrowser(t *testing.T) browser.Browser {
	t.Helper()
	cfg := browser.DefaultBrowserConfig()
	cfg.DefaultTimeout = 15 * time.Second
	cfg.MinIntervalPerHost = 0 // No rate limiting in tests

	b, err := browser.New(cfg, nil)
	if err != nil {
		t.Fatalf("browser.New: %v", err)
	}
	t.Cleanup(func() {
		if err := b.Close(); err != nil {
			t.Logf("browser.Close: %v", err)
		}
	})
	return b
}

// TestIntegration_FetchHTML_StaticPage verifies that FetchHTML returns the server-
// rendered HTML of a simple httptest.Server page.
func TestIntegration_FetchHTML_StaticPage(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`<html><body><h1 id="title">Hello CardexBot</h1></body></html>`))
	}))
	defer srv.Close()

	b := newTestBrowser(t)
	result, err := b.FetchHTML(context.Background(), srv.URL, &browser.FetchOptions{
		WaitForNetworkIdle: true,
	})
	if err != nil {
		t.Fatalf("FetchHTML: %v", err)
	}
	if result.StatusCode != 200 {
		t.Errorf("StatusCode = %d, want 200", result.StatusCode)
	}
	if !strings.Contains(result.HTML, "Hello CardexBot") {
		t.Errorf("HTML does not contain expected content; got (first 500 chars): %.500s", result.HTML)
	}
}

// TestIntegration_FetchHTML_WaitForSelector verifies that WaitForSelector delays
// return until the target element appears (injected by a JS setTimeout).
func TestIntegration_FetchHTML_WaitForSelector(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		// JS inserts #delayed-content after 300ms.
		_, _ = w.Write([]byte(`<html><body>
<div id="container"></div>
<script>
setTimeout(function(){
  var d = document.createElement("div");
  d.id = "delayed-content";
  d.textContent = "Loaded";
  document.getElementById("container").appendChild(d);
}, 300);
</script>
</body></html>`))
	}))
	defer srv.Close()

	b := newTestBrowser(t)
	result, err := b.FetchHTML(context.Background(), srv.URL, &browser.FetchOptions{
		WaitForNetworkIdle: false,
		WaitForSelector:    "#delayed-content",
	})
	if err != nil {
		t.Fatalf("FetchHTML with WaitForSelector: %v", err)
	}
	if !strings.Contains(result.HTML, "delayed-content") {
		t.Error("expected #delayed-content in HTML; WaitForSelector may not have waited")
	}
}

// TestIntegration_Screenshot_PNG verifies that Screenshot returns a non-empty PNG.
func TestIntegration_Screenshot_PNG(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<html><body style="background:white"><h1>Screenshot Test</h1></body></html>`))
	}))
	defer srv.Close()

	b := newTestBrowser(t)
	result, err := b.Screenshot(context.Background(), srv.URL, &browser.ScreenshotOptions{
		FullPage: true,
		Format:   "png",
	})
	if err != nil {
		t.Fatalf("Screenshot: %v", err)
	}
	if len(result.ImageBytes) == 0 {
		t.Error("ImageBytes is empty")
	}
	if result.Format != "png" {
		t.Errorf("Format = %q, want %q", result.Format, "png")
	}
	if result.Width == 0 || result.Height == 0 {
		t.Errorf("image dimensions = %dx%d, want non-zero", result.Width, result.Height)
	}
	// Verify PNG magic bytes.
	if len(result.ImageBytes) < 8 || string(result.ImageBytes[:4]) != "\x89PNG" {
		t.Error("ImageBytes does not start with PNG magic bytes")
	}
}

// TestIntegration_InterceptXHR verifies that InterceptXHR captures a fetch()
// call made by a page's JavaScript.
func TestIntegration_InterceptXHR(t *testing.T) {
	// The API endpoint: returns a JSON payload.
	apiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"dealers":[{"name":"Test Dealer"}]}`))
	}))
	defer apiSrv.Close()

	// The SPA page: makes a fetch() to the API endpoint.
	html := `<html><body>
<script>
fetch('` + apiSrv.URL + `/api/dealers').then(r => r.json()).then(d => {
  document.body.setAttribute('data-loaded','true');
});
</script>
</body></html>`

	spaSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(html))
	}))
	defer spaSrv.Close()

	b := newTestBrowser(t)
	captures, err := b.InterceptXHR(context.Background(), spaSrv.URL, browser.XHRFilter{
		URLPattern:    "/api/dealers",
		MethodFilter:  []string{"GET"},
		MinStatusCode: 200,
	})
	if err != nil {
		t.Fatalf("InterceptXHR: %v", err)
	}
	if len(captures) == 0 {
		t.Error("expected at least one XHR capture for /api/dealers, got none")
	}
	if len(captures) > 0 {
		c := captures[0]
		if !strings.Contains(c.RequestURL, "/api/dealers") {
			t.Errorf("RequestURL = %q, want to contain /api/dealers", c.RequestURL)
		}
		if c.ResponseStatus != 200 {
			t.Errorf("ResponseStatus = %d, want 200", c.ResponseStatus)
		}
		if !strings.Contains(string(c.ResponseBody), "dealers") {
			t.Errorf("ResponseBody = %q, want dealers JSON", string(c.ResponseBody))
		}
	}
}

// TestIntegration_GracefulShutdown verifies that Close() does not panic and
// returns no error even when called with open sessions.
func TestIntegration_GracefulShutdown(t *testing.T) {
	cfg := browser.DefaultBrowserConfig()
	cfg.DefaultTimeout = 10 * time.Second
	cfg.MinIntervalPerHost = 0

	b, err := browser.New(cfg, nil)
	if err != nil {
		t.Fatalf("browser.New: %v", err)
	}

	// Open a page (creates a context in the pool).
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`<html><body>shutdown test</body></html>`))
	}))
	defer srv.Close()

	_, _ = b.FetchHTML(context.Background(), srv.URL, nil)

	// Close should succeed without panic.
	if err := b.Close(); err != nil {
		t.Errorf("Close: %v", err)
	}
}
