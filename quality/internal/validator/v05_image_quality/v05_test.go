package v05_image_quality_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v05_image_quality"
)

// minimalJPEG is a 2-byte JPEG magic number prefix followed by filler to exceed 30 KB.
var minimalJPEG = func() []byte {
	b := make([]byte, 32*1024)
	b[0] = 0xFF
	b[1] = 0xD8
	return b
}()

func vehicle(urls ...string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", PhotoURLs: urls}
}

// TestV05_ValidJPEG verifies that a properly-sized JPEG photo URL passes.
func TestV05_ValidJPEG(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/jpeg")
		w.Header().Set("Content-Length", "51200") // 50 KB
		if r.Method == http.MethodGet {
			w.Write(minimalJPEG)
		}
	}))
	defer srv.Close()

	val := v05_image_quality.NewWithClient(srv.Client(), 0)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/photo.jpg"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for valid JPEG, issue: %s", res.Issue)
	}
}

// TestV05_InvalidContentType verifies that an HTML response (wrong type) is CRITICAL.
func TestV05_InvalidContentType(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Header().Set("Content-Length", "51200")
	}))
	defer srv.Close()

	val := v05_image_quality.NewWithClient(srv.Client(), 0)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/photo.jpg"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for text/html content-type, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want severity CRITICAL for wrong content-type, got %s", res.Severity)
	}
}

// TestV05_SmallFile verifies that a file below 30 KB produces a WARNING.
func TestV05_SmallFile(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "image/jpeg")
		w.Header().Set("Content-Length", "5120") // 5 KB — tiny thumbnail
	}))
	defer srv.Close()

	val := v05_image_quality.NewWithClient(srv.Client(), 0)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/thumb.jpg"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for tiny file, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want severity WARNING for small file, got %s", res.Severity)
	}
}

// TestV05_LowResolution verifies that CDN dimension headers below 800x600 give WARNING.
func TestV05_LowResolution(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "image/jpeg")
		w.Header().Set("Content-Length", "51200")
		w.Header().Set("X-Image-Width", "400")
		w.Header().Set("X-Image-Height", "300")
	}))
	defer srv.Close()

	val := v05_image_quality.NewWithClient(srv.Client(), 0)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/lowres.jpg"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 400x300 image, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for low-res image, got %s", res.Severity)
	}
}

// TestV05_NoPhotos verifies that a vehicle with no photos is skipped with INFO.
func TestV05_NoPhotos(t *testing.T) {
	val := v05_image_quality.New()
	res, err := val.Validate(context.Background(), &pipeline.Vehicle{InternalID: "T5"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true when no photos (INFO skip)")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO when no photos, got %s", res.Severity)
	}
}

// TestV05_404Photo verifies that a 404 response produces a CRITICAL failure.
func TestV05_404Photo(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	val := v05_image_quality.NewWithClient(srv.Client(), 0)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/missing.jpg"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 404 photo, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 404 photo, got %s", res.Severity)
	}
}
