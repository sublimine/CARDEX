package v16_photo_phash_test

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v16_photo_phash"
)

// encodePNG encodes an image.Image to PNG bytes.
func encodePNG(img image.Image) []byte {
	var buf bytes.Buffer
	_ = png.Encode(&buf, img)
	return buf.Bytes()
}

// makeImage creates a simple gradient image of the given size.
func makeImage(w, h int, baseR, baseG, baseB uint8) image.Image {
	img := image.NewNRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.NRGBA{
				R: baseR + uint8(x%10),
				G: baseG + uint8(y%10),
				B: baseB,
				A: 255,
			})
		}
	}
	return img
}

// mockHashStore records stored hashes and returns configurable FindSimilar results.
type mockHashStore struct {
	stored   map[string]uint64 // photoURL → hash
	findResp []string          // vehicleIDs to return on FindSimilar
	findErr  error
}

func (m *mockHashStore) FindSimilar(_ context.Context, _ uint64, _ int, _ string) ([]string, error) {
	return m.findResp, m.findErr
}

func (m *mockHashStore) StoreHash(_ context.Context, _, url string, hash uint64) error {
	if m.stored == nil {
		m.stored = make(map[string]uint64)
	}
	m.stored[url] = hash
	return nil
}

// imageServer returns an httptest.Server serving the given PNG bytes for every request.
func imageServer(imgBytes []byte) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(imgBytes)
	}))
}

// TestV16_NoPhotos verifies that a vehicle with no photos passes INFO.
func TestV16_NoPhotos(t *testing.T) {
	val := v16_photo_phash.New()
	res, err := val.Validate(context.Background(), &pipeline.Vehicle{InternalID: "V1"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for no photos, got false: %s", res.Issue)
	}
}

// TestV16_NoDuplicates verifies that unique photos pass.
func TestV16_NoDuplicates(t *testing.T) {
	imgBytes := encodePNG(makeImage(64, 64, 200, 100, 50))
	srv := imageServer(imgBytes)
	defer srv.Close()

	store := &mockHashStore{findResp: nil} // no duplicates found
	val := v16_photo_phash.NewWithStore(srv.Client(), store)

	res, err := val.Validate(context.Background(), &pipeline.Vehicle{
		InternalID: "V1",
		PhotoURLs:  []string{srv.URL + "/img1.png"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for unique photos, got false: %s", res.Issue)
	}
	if store.stored == nil || len(store.stored) == 0 {
		t.Error("expected pHash to be stored in HashStore")
	}
}

// TestV16_DuplicateDetected verifies that a duplicate photo triggers WARNING.
func TestV16_DuplicateDetected(t *testing.T) {
	imgBytes := encodePNG(makeImage(64, 64, 128, 64, 32))
	srv := imageServer(imgBytes)
	defer srv.Close()

	store := &mockHashStore{findResp: []string{"OTHER_VEHICLE_123"}}
	val := v16_photo_phash.NewWithStore(srv.Client(), store)

	res, err := val.Validate(context.Background(), &pipeline.Vehicle{
		InternalID: "V2",
		PhotoURLs:  []string{srv.URL + "/img.png"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false when duplicate photo found")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for duplicate photo, got %s", res.Severity)
	}
	if res.Evidence["duplicate_vehicle_ids"] == "" {
		t.Error("expected duplicate_vehicle_ids evidence to be set")
	}
}

// TestV16_HTTPError verifies soft-fail when image fetch fails.
func TestV16_HTTPError(t *testing.T) {
	// Server that returns 500.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	store := &mockHashStore{}
	val := v16_photo_phash.NewWithStore(srv.Client(), store)

	res, err := val.Validate(context.Background(), &pipeline.Vehicle{
		InternalID: "V3",
		PhotoURLs:  []string{srv.URL + "/bad.png"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should pass (soft-fail) — fetch error does not block the pipeline.
	if !res.Pass {
		t.Errorf("want pass=true (soft-fail) on fetch error, got false: %s", res.Issue)
	}
}

// TestV16_HammingDistance verifies the exported helper returns correct distances.
func TestV16_HammingDistance(t *testing.T) {
	tests := []struct {
		a, b uint64
		want int
	}{
		{0, 0, 0},
		{0xFFFFFFFFFFFFFFFF, 0, 64},
		{0b1111, 0b0000, 4},
		{0b1010, 0b1100, 2},
	}
	for _, tt := range tests {
		got := v16_photo_phash.HammingDistance(tt.a, tt.b)
		if got != tt.want {
			t.Errorf("HammingDistance(%064b, %064b) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}
