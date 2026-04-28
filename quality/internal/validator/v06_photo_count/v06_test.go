package v06_photo_count_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v06_photo_count"
)

func makeURLs(n int) []string {
	urls := make([]string, n)
	for i := range urls {
		urls[i] = "https://cdn.example.com/photo.jpg"
	}
	return urls
}

func vehicle(n int) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", PhotoURLs: makeURLs(n)}
}

// TestV06_ZeroPhotos verifies that 0 photos is a CRITICAL failure.
func TestV06_ZeroPhotos(t *testing.T) {
	val := v06_photo_count.New()
	res, err := val.Validate(context.Background(), vehicle(0))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 0 photos, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 0 photos, got %s", res.Severity)
	}
}

// TestV06_OnePhoto verifies that 1 photo produces a WARNING failure.
func TestV06_OnePhoto(t *testing.T) {
	val := v06_photo_count.New()
	res, err := val.Validate(context.Background(), vehicle(1))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 1 photo, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for 1 photo, got %s", res.Severity)
	}
}

// TestV06_ThreePhotos verifies that 3 photos produces an INFO pass (acceptable wholesale).
func TestV06_ThreePhotos(t *testing.T) {
	val := v06_photo_count.New()
	res, err := val.Validate(context.Background(), vehicle(3))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 3 photos, issue: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for 3 photos, got %s", res.Severity)
	}
}

// TestV06_SixPhotos verifies that 6 photos is a full pass.
func TestV06_SixPhotos(t *testing.T) {
	val := v06_photo_count.New()
	res, err := val.Validate(context.Background(), vehicle(6))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 6 photos, issue: %s", res.Issue)
	}
}

// TestV06_TenPhotos verifies that 10 photos passes with max confidence.
func TestV06_TenPhotos(t *testing.T) {
	val := v06_photo_count.New()
	res, err := val.Validate(context.Background(), vehicle(10))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 10 photos, issue: %s", res.Issue)
	}
	if res.Confidence != 1.0 {
		t.Errorf("want confidence 1.0 for 10 photos, got %f", res.Confidence)
	}
}
