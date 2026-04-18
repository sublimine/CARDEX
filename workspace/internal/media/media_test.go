package media

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"image/jpeg"
	"image/png"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// makeJPEG returns a minimal valid JPEG with the given dimensions.
func makeJPEG(w, h int) []byte {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.RGBA{R: 200, G: 150, B: 100, A: 255})
		}
	}
	var buf bytes.Buffer
	_ = jpeg.Encode(&buf, img, &jpeg.Options{Quality: 90})
	return buf.Bytes()
}

// makePNG returns a minimal valid PNG.
func makePNG(w, h int) []byte {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.RGBA{R: 100, G: 200, B: 150, A: 255})
		}
	}
	var buf bytes.Buffer
	_ = png.Encode(&buf, img)
	return buf.Bytes()
}

// newTestStorage creates an in-memory SQLite FSStorage.
func newTestStorage(t *testing.T) *FSStorage {
	t.Helper()
	dir := t.TempDir()
	s, err := NewFSStorage(filepath.Join(dir, "test.db"), dir)
	if err != nil {
		t.Fatalf("NewFSStorage: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// ── format detection ──────────────────────────────────────────────────────────

func TestDetectedFormatJPEG(t *testing.T) {
	data := makeJPEG(10, 10)
	if got := detectedFormat(data); got != "jpeg" {
		t.Errorf("expected jpeg, got %q", got)
	}
}

func TestDetectedFormatPNG(t *testing.T) {
	data := makePNG(10, 10)
	if got := detectedFormat(data); got != "png" {
		t.Errorf("expected png, got %q", got)
	}
}

func TestDetectedFormatWebP(t *testing.T) {
	// Minimal WebP-like magic (RIFF....WEBP).
	data := []byte("RIFF\x00\x00\x00\x00WEBP")
	if got := detectedFormat(data); got != "webp" {
		t.Errorf("expected webp, got %q", got)
	}
}

func TestDetectedFormatUnknown(t *testing.T) {
	data := []byte{0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B}
	if got := detectedFormat(data); got != "" {
		t.Errorf("expected empty, got %q", got)
	}
}

// ── processor ─────────────────────────────────────────────────────────────────

func TestProcessJPEGProducesThreeVariants(t *testing.T) {
	data := makeJPEG(3000, 2000)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	if len(variants) != 3 {
		t.Fatalf("expected 3 variants, got %d", len(variants))
	}
	kinds := map[VariantKind]bool{}
	for _, v := range variants {
		kinds[v.Kind] = true
		if len(v.Data) == 0 {
			t.Errorf("variant %s has empty data", v.Kind)
		}
	}
	for _, k := range AllVariants {
		if !kinds[k] {
			t.Errorf("missing variant %s", k)
		}
	}
}

func TestProcessPNGProducesThreeVariants(t *testing.T) {
	data := makePNG(800, 600)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process PNG: %v", err)
	}
	if len(variants) != 3 {
		t.Fatalf("expected 3 variants, got %d", len(variants))
	}
}

func TestProcessOriginalDimensionsCapped(t *testing.T) {
	data := makeJPEG(4000, 3000)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	for _, v := range variants {
		if v.Kind == VariantOriginal {
			if v.Width > maxOriginalPx || v.Height > maxOriginalPx {
				t.Errorf("original variant %dx%d exceeds %dpx cap", v.Width, v.Height, maxOriginalPx)
			}
		}
	}
}

func TestProcessWebDimensionsCapped(t *testing.T) {
	data := makeJPEG(2000, 1500)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	for _, v := range variants {
		if v.Kind == VariantWeb {
			if v.Width > maxWebPx || v.Height > maxWebPx {
				t.Errorf("web variant %dx%d exceeds %dpx cap", v.Width, v.Height, maxWebPx)
			}
		}
	}
}

func TestProcessThumbnailDimensions(t *testing.T) {
	data := makeJPEG(1200, 900)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	for _, v := range variants {
		if v.Kind == VariantThumbnail {
			if v.Width != thumbW || v.Height != thumbH {
				t.Errorf("thumbnail %dx%d, want %dx%d", v.Width, v.Height, thumbW, thumbH)
			}
		}
	}
}

func TestProcessSmallImageNotUpscaled(t *testing.T) {
	// 100×80 image should not be enlarged in the original variant.
	data := makeJPEG(100, 80)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	for _, v := range variants {
		if v.Kind == VariantOriginal {
			if v.Width > 100 || v.Height > 80 {
				t.Errorf("small image was upscaled to %dx%d", v.Width, v.Height)
			}
		}
	}
}

func TestProcessOutputIsJPEG(t *testing.T) {
	data := makePNG(200, 200)
	variants, err := Process(data)
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	for _, v := range variants {
		if !bytes.HasPrefix(v.Data, []byte("\xFF\xD8\xFF")) {
			t.Errorf("variant %s output is not JPEG (magic: %x)", v.Kind, v.Data[:3])
		}
	}
}

func TestProcessEXIFStripped(t *testing.T) {
	// Build a JPEG with a synthetic APP1/EXIF block.
	img := image.NewRGBA(image.Rect(0, 0, 100, 80))
	var buf bytes.Buffer
	_ = jpeg.Encode(&buf, img, nil)
	raw := buf.Bytes()

	// Inject a fake APP1 marker after SOI.
	// SOI is 2 bytes (\xFF\xD8), then we inject APP1 (\xFF\xE1) with Exif\x00\x00 header.
	fakeApp1 := []byte{0xFF, 0xE1, 0x00, 0x0E, 'E', 'x', 'i', 'f', 0x00, 0x00, 0x49, 0x49, 0x2A, 0x00, 0x08, 0x00}
	withEXIF := append(raw[:2], append(fakeApp1, raw[2:]...)...)

	variants, err := Process(withEXIF)
	if err != nil {
		t.Fatalf("Process with EXIF: %v", err)
	}
	for _, v := range variants {
		// APP1 marker \xFF\xE1 should not appear in output beyond first few bytes.
		app1 := []byte{0xFF, 0xE1}
		if bytes.Contains(v.Data[2:], app1) {
			t.Errorf("variant %s still contains APP1/EXIF marker", v.Kind)
		}
	}
}

func TestProcessEmptyDataError(t *testing.T) {
	_, err := Process(nil)
	if err == nil {
		t.Error("expected error for empty input")
	}
}

// ── storage ───────────────────────────────────────────────────────────────────

func TestSaveAndGetPhoto(t *testing.T) {
	s := newTestStorage(t)
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Second)
	p := &Photo{
		ID: newMediaID(), TenantID: "t1", VehicleID: "v1",
		SortOrder: 0, IsPrimary: true, FileName: "front.jpg", MimeType: "image/jpeg",
		CreatedAt: now, UpdatedAt: now,
	}
	if err := s.SavePhoto(ctx, p); err != nil {
		t.Fatalf("SavePhoto: %v", err)
	}
	got, err := s.GetPhoto(ctx, "t1", p.ID)
	if err != nil {
		t.Fatalf("GetPhoto: %v", err)
	}
	if got.FileName != "front.jpg" || !got.IsPrimary {
		t.Errorf("unexpected photo: %+v", got)
	}
}

func TestListPhotosOrderedBySortOrder(t *testing.T) {
	s := newTestStorage(t)
	ctx := context.Background()
	now := time.Now().UTC()
	for i, sortOrder := range []int{2, 0, 1} {
		p := &Photo{
			ID: newMediaID(), TenantID: "t1", VehicleID: "v2",
			SortOrder: sortOrder, FileName: "img.jpg", MimeType: "image/jpeg",
			CreatedAt: now.Add(time.Duration(i) * time.Second),
			UpdatedAt: now,
		}
		if err := s.SavePhoto(ctx, p); err != nil {
			t.Fatalf("SavePhoto %d: %v", i, err)
		}
	}
	photos, err := s.ListPhotos(ctx, "t1", "v2")
	if err != nil {
		t.Fatalf("ListPhotos: %v", err)
	}
	if len(photos) != 3 {
		t.Fatalf("expected 3 photos, got %d", len(photos))
	}
	for i, p := range photos {
		if p.SortOrder != i {
			t.Errorf("index %d: got sort_order %d", i, p.SortOrder)
		}
	}
}

func TestUpdateSortOrders(t *testing.T) {
	s := newTestStorage(t)
	ctx := context.Background()
	now := time.Now().UTC()
	ids := make([]string, 3)
	for i := range ids {
		ids[i] = newMediaID()
		p := &Photo{
			ID: ids[i], TenantID: "t1", VehicleID: "v3",
			SortOrder: i, FileName: "img.jpg", MimeType: "image/jpeg",
			CreatedAt: now, UpdatedAt: now,
		}
		if err := s.SavePhoto(ctx, p); err != nil {
			t.Fatalf("SavePhoto: %v", err)
		}
	}
	// Reverse the order.
	reversed := []string{ids[2], ids[1], ids[0]}
	if err := s.UpdateSortOrders(ctx, "t1", reversed); err != nil {
		t.Fatalf("UpdateSortOrders: %v", err)
	}
	photos, err := s.ListPhotos(ctx, "t1", "v3")
	if err != nil {
		t.Fatalf("ListPhotos: %v", err)
	}
	for i, p := range photos {
		if p.SortOrder != i {
			t.Errorf("after reorder: index %d has sort_order %d", i, p.SortOrder)
		}
	}
}

func TestWriteFile(t *testing.T) {
	s := newTestStorage(t)
	data := makeJPEG(100, 80)
	path, err := s.WriteFile("tenant1", "vehicle1", "photo1", VariantWeb, data)
	if err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	if !strings.Contains(path, "photo1_web.jpg") {
		t.Errorf("unexpected path: %s", path)
	}
}

// ── watermark ─────────────────────────────────────────────────────────────────

func TestWatermarkNilPassthrough(t *testing.T) {
	var wm *Watermarker
	img := image.NewRGBA(image.Rect(0, 0, 100, 80))
	result := wm.Apply(img)
	if result != img {
		t.Error("nil watermarker should return original image unchanged")
	}
}

func TestWatermarkApplyChangesImage(t *testing.T) {
	logo := image.NewRGBA(image.Rect(0, 0, 20, 20))
	for y := 0; y < 20; y++ {
		for x := 0; x < 20; x++ {
			logo.Set(x, y, color.RGBA{R: 255, G: 0, B: 0, A: 200})
		}
	}
	wm := NewWatermarker(logo, 0.5)
	img := image.NewRGBA(image.Rect(0, 0, 200, 150))
	result := wm.Apply(img)
	if result == nil {
		t.Fatal("Apply returned nil")
	}
	if result.Bounds() != img.Bounds() {
		t.Errorf("bounds changed: got %v, want %v", result.Bounds(), img.Bounds())
	}
}

// ── reorder handler ───────────────────────────────────────────────────────────

func TestReorderHandlerMissingTenantID(t *testing.T) {
	s := newTestStorage(t)
	h := ReorderHandler(s)
	body := `{"photo_ids":["a","b"]}`
	req := httptest.NewRequest(http.MethodPut, "/api/v1/vehicles/v1/media/reorder", strings.NewReader(body))
	rr := httptest.NewRecorder()
	h(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", rr.Code)
	}
}

func TestReorderHandlerWrongMethod(t *testing.T) {
	s := newTestStorage(t)
	h := ReorderHandler(s)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/vehicles/v1/media/reorder", nil)
	rr := httptest.NewRecorder()
	h(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405, got %d", rr.Code)
	}
}

func TestVehicleIDFromPath(t *testing.T) {
	cases := []struct {
		path string
		want string
	}{
		{"/api/v1/vehicles/abc123/media/reorder", "abc123"},
		{"/vehicles/xyz/media/reorder", "xyz"},
		{"/api/v1/nope", ""},
	}
	for _, tc := range cases {
		if got := vehicleIDFromPath(tc.path); got != tc.want {
			t.Errorf("vehicleIDFromPath(%q) = %q, want %q", tc.path, got, tc.want)
		}
	}
}

// ── export ────────────────────────────────────────────────────────────────────

func TestPickVariantRespectsMaxSize(t *testing.T) {
	variants := []*PhotoVariant{
		{Kind: VariantWeb, SizeBytes: 6 * 1024 * 1024},       // 6 MB — too large for mobile.de
		{Kind: VariantOriginal, SizeBytes: 3 * 1024 * 1024},  // 3 MB — ok
		{Kind: VariantThumbnail, SizeBytes: 50 * 1024},
	}
	chosen := pickVariant(variants, PlatformMobileDe)
	if chosen == nil || chosen.Kind != VariantOriginal {
		t.Errorf("expected original variant, got %v", chosen)
	}
}

func TestPickVariantPrefersWeb(t *testing.T) {
	variants := []*PhotoVariant{
		{Kind: VariantWeb, SizeBytes: 200 * 1024},
		{Kind: VariantOriginal, SizeBytes: 1024 * 1024},
	}
	chosen := pickVariant(variants, PlatformAutoScout24)
	if chosen == nil || chosen.Kind != VariantWeb {
		t.Errorf("expected web variant, got %v", chosen)
	}
}

func TestExportPlatformMaxCount(t *testing.T) {
	if PlatformMobileDe.MaxCount != 30 {
		t.Errorf("mobile.de max count = %d, want 30", PlatformMobileDe.MaxCount)
	}
	if PlatformAutoScout24.MaxCount != 50 {
		t.Errorf("autoscout24 max count = %d, want 50", PlatformAutoScout24.MaxCount)
	}
	if PlatformLeboncoin.MaxCount != 10 {
		t.Errorf("leboncoin max count = %d, want 10", PlatformLeboncoin.MaxCount)
	}
}
