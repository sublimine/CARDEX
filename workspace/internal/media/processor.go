package media

import (
	"bytes"
	"fmt"
	"image"
	"image/jpeg"
	"io"
	"time"

	"github.com/disintegration/imaging"
	"github.com/jdeng/goheif"
)

const (
	maxOriginalPx  = 2048
	maxWebPx       = 1024
	thumbW, thumbH = 400, 300
	webQuality     = 85
	thumbQuality   = 75
	origQuality    = 92
	maxWebKB       = 800
)

// detectedFormat identifies the image container from magic bytes.
func detectedFormat(data []byte) string {
	if len(data) < 12 {
		return ""
	}
	switch {
	case bytes.HasPrefix(data, []byte("\xFF\xD8\xFF")):
		return "jpeg"
	case bytes.HasPrefix(data, []byte("\x89PNG\r\n\x1a\n")):
		return "png"
	// WebP: RIFF????WEBP
	case len(data) >= 12 && bytes.HasPrefix(data, []byte("RIFF")) && bytes.Equal(data[8:12], []byte("WEBP")):
		return "webp"
	// HEIC/HEIF ftyp box
	case len(data) >= 12 && (bytes.Contains(data[4:12], []byte("heic")) || bytes.Contains(data[4:12], []byte("hei ")) || bytes.Contains(data[4:12], []byte("mif1"))):
		return "heic"
	}
	return ""
}

// decodeImage decodes any supported format to image.Image.
// For JPEG/PNG/WebP the disintegration/imaging library handles auto-orientation
// and EXIF stripping by re-encoding. For HEIC we delegate to goheif.
func decodeImage(data []byte, format string) (image.Image, error) {
	switch format {
	case "heic":
		r := bytes.NewReader(data)
		img, err := goheif.Decode(r)
		if err != nil {
			return nil, fmt.Errorf("heic decode: %w", err)
		}
		return img, nil
	case "jpeg", "png", "webp", "":
		// imaging.Decode with AutoOrientation applies rotation from EXIF and drops
		// the EXIF block when the image is re-encoded, satisfying the privacy strip
		// requirement.
		r := bytes.NewReader(data)
		img, err := imaging.Decode(r, imaging.AutoOrientation(true))
		if err != nil {
			return nil, fmt.Errorf("imaging decode: %w", err)
		}
		return img, nil
	default:
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedFormat, format)
	}
}

// encodeJPEG encodes img to JPEG at the given quality, returning raw bytes.
func encodeJPEG(img image.Image, quality int) ([]byte, error) {
	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: quality}); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// resizeFit shrinks img so that neither side exceeds maxPx, preserving aspect
// ratio. If the image is already within bounds it is returned unchanged.
func resizeFit(img image.Image, maxPx int) image.Image {
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	if w <= maxPx && h <= maxPx {
		return img
	}
	if w >= h {
		return imaging.Resize(img, maxPx, 0, imaging.Lanczos)
	}
	return imaging.Resize(img, 0, maxPx, imaging.Lanczos)
}

// resizeCrop returns a centre-cropped image of exactly w×h pixels.
func resizeCrop(img image.Image, w, h int) image.Image {
	return imaging.Fill(img, w, h, imaging.Center, imaging.Lanczos)
}

// Process decodes raw image bytes and returns three variants (original, web,
// thumbnail). EXIF metadata is stripped during decode/re-encode. Orientation is
// preserved by applying any EXIF rotation before stripping.
func Process(data []byte) ([]*ProcessedVariant, error) {
	if len(data) == 0 {
		return nil, ErrUnsupportedFormat
	}

	format := detectedFormat(data)
	if format == "" {
		// fall back to imaging detection
		format = "jpeg"
	}

	src, err := decodeImage(data, format)
	if err != nil {
		return nil, err
	}

	variants := make([]*ProcessedVariant, 0, 3)

	// ── Original variant ──────────────────────────────────────────────────────
	t0 := time.Now()
	origImg := resizeFit(src, maxOriginalPx)
	origBytes, err := encodeJPEG(origImg, origQuality)
	if err != nil {
		return nil, fmt.Errorf("encode original: %w", err)
	}
	b := origImg.Bounds()
	variants = append(variants, &ProcessedVariant{
		Kind:   VariantOriginal,
		Data:   origBytes,
		Width:  b.Dx(),
		Height: b.Dy(),
		SizeKB: len(origBytes) / 1024,
	})
	processingDuration.WithLabelValues(string(VariantOriginal)).Observe(time.Since(t0).Seconds())
	storageBytesTotal.WithLabelValues(string(VariantOriginal)).Add(float64(len(origBytes)))

	// ── Web variant ───────────────────────────────────────────────────────────
	t1 := time.Now()
	webImg := resizeFit(src, maxWebPx)
	webBytes, err := encodeJPEG(webImg, webQuality)
	if err != nil {
		return nil, fmt.Errorf("encode web: %w", err)
	}
	// If the web output exceeds 800 KB, lower quality until it fits.
	q := webQuality
	for len(webBytes) > maxWebKB*1024 && q > 50 {
		q -= 5
		webBytes, err = encodeJPEG(webImg, q)
		if err != nil {
			return nil, fmt.Errorf("encode web (quality reduce): %w", err)
		}
	}
	wb := webImg.Bounds()
	variants = append(variants, &ProcessedVariant{
		Kind:   VariantWeb,
		Data:   webBytes,
		Width:  wb.Dx(),
		Height: wb.Dy(),
		SizeKB: len(webBytes) / 1024,
	})
	processingDuration.WithLabelValues(string(VariantWeb)).Observe(time.Since(t1).Seconds())
	storageBytesTotal.WithLabelValues(string(VariantWeb)).Add(float64(len(webBytes)))

	// ── Thumbnail variant ─────────────────────────────────────────────────────
	t2 := time.Now()
	thumbImg := resizeCrop(src, thumbW, thumbH)
	thumbBytes, err := encodeJPEG(thumbImg, thumbQuality)
	if err != nil {
		return nil, fmt.Errorf("encode thumbnail: %w", err)
	}
	variants = append(variants, &ProcessedVariant{
		Kind:   VariantThumbnail,
		Data:   thumbBytes,
		Width:  thumbW,
		Height: thumbH,
		SizeKB: len(thumbBytes) / 1024,
	})
	processingDuration.WithLabelValues(string(VariantThumbnail)).Observe(time.Since(t2).Seconds())
	storageBytesTotal.WithLabelValues(string(VariantThumbnail)).Add(float64(len(thumbBytes)))

	return variants, nil
}

// ProcessReader is a convenience wrapper that reads from r before calling Process.
func ProcessReader(r io.Reader) ([]*ProcessedVariant, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}
	return Process(data)
}
