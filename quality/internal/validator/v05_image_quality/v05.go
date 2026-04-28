// Package v05_image_quality implements validation strategy V05 — Image Quality.
//
// # Strategy
//
// Each vehicle photo URL is probed with a HEAD request. The validator checks:
//
//  1. Content-Type must be image/jpeg, image/png, image/webp, or image/avif.
//  2. Content-Length (if present) must be ≥ 30 KB (placeholder/thumbnail guard).
//  3. X-Image-Width / X-Image-Height CDN headers, if present, must meet 800×600.
//  4. If Content-Length < 1 MiB, fetches the first 12 bytes for magic-number check.
//
// The vehicle passes only when all photos pass. The first CRITICAL failure
// (wrong content-type or magic-number mismatch) short-circuits remaining photos.
//
// Severity: CRITICAL for wrong content-type; WARNING for size/resolution hints.
package v05_image_quality

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V05"
	strategyName = "Image Quality"

	minBytes       = 30 * 1024 // 30 KB minimum useful photo
	minWidth       = 800
	minHeight      = 600
	headTimeout    = 3 * time.Second
	magicReadBytes = 12
)

var (
	allowedTypes = map[string]bool{
		"image/jpeg": true,
		"image/png":  true,
		"image/webp": true,
		"image/avif": true,
	}

	// magic signatures: type → prefix bytes
	magicSigs = map[string][]byte{
		"image/jpeg": {0xFF, 0xD8},
		"image/png":  {0x89, 0x50, 0x4E, 0x47},
		"image/webp": {0x52, 0x49, 0x46, 0x46}, // "RIFF"
	}
)

// ImageQuality implements pipeline.Validator for V05.
type ImageQuality struct {
	client      *http.Client
	rateLimitMs int
}

// New returns an ImageQuality validator with default HTTP client.
func New() *ImageQuality {
	return NewWithClient(&http.Client{Timeout: 10 * time.Second}, 500)
}

// NewWithClient returns an ImageQuality validator with a custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *ImageQuality {
	return &ImageQuality{client: c, rateLimitMs: rateLimitMs}
}

func (v *ImageQuality) ID() string                 { return strategyID }
func (v *ImageQuality) Name() string               { return strategyName }
func (v *ImageQuality) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate probes every photo URL and returns an aggregate result.
func (v *ImageQuality) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityWarning,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	if len(vehicle.PhotoURLs) == 0 {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no photo URLs to validate"
		result.Confidence = 1.0
		return result, nil
	}

	result.Evidence["photo_count"] = strconv.Itoa(len(vehicle.PhotoURLs))

	var issues []string
	worstSeverity := pipeline.SeverityInfo

	for i, url := range vehicle.PhotoURLs {
		if ctx.Err() != nil {
			break
		}
		if v.rateLimitMs > 0 && i > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(time.Duration(v.rateLimitMs) * time.Millisecond):
			}
		}

		sev, issue := v.checkPhoto(ctx, url, i+1)
		if issue != "" {
			issues = append(issues, fmt.Sprintf("photo %d: %s", i+1, issue))
			if sev == pipeline.SeverityCritical {
				worstSeverity = pipeline.SeverityCritical
				break // short-circuit on critical
			}
			if sev == pipeline.SeverityWarning && worstSeverity == pipeline.SeverityInfo {
				worstSeverity = pipeline.SeverityWarning
			}
		}
	}

	if len(issues) == 0 {
		result.Pass = true
		result.Confidence = 0.9
		result.Severity = pipeline.SeverityInfo
	} else {
		result.Pass = false
		result.Severity = worstSeverity
		result.Issue = strings.Join(issues, "; ")
		result.Confidence = 0.9
	}
	return result, nil
}

// checkPhoto probes a single photo URL and returns the severity and issue string.
// An empty issue string means pass.
func (v *ImageQuality) checkPhoto(ctx context.Context, url string, _ int) (pipeline.Severity, string) {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return pipeline.SeverityWarning, "invalid URL: " + err.Error()
	}

	resp, err := v.client.Do(req)
	if err != nil {
		return pipeline.SeverityWarning, "HEAD request failed: " + err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		sev := pipeline.SeverityWarning
		if resp.StatusCode == http.StatusNotFound || resp.StatusCode == http.StatusGone {
			sev = pipeline.SeverityCritical
		}
		return sev, fmt.Sprintf("HTTP %d", resp.StatusCode)
	}

	// 1. Content-Type check.
	ct := strings.ToLower(strings.SplitN(resp.Header.Get("Content-Type"), ";", 2)[0])
	ct = strings.TrimSpace(ct)
	if !allowedTypes[ct] {
		return pipeline.SeverityCritical, "invalid content-type: " + ct
	}

	// 2. Content-Length check.
	if cl := resp.ContentLength; cl > 0 && cl < int64(minBytes) {
		return pipeline.SeverityWarning, fmt.Sprintf("file too small: %d bytes (min %d)", cl, minBytes)
	}

	// 3. CDN dimension headers.
	if w, h := parseDimHeader(resp.Header); w > 0 && h > 0 {
		if w < minWidth || h < minHeight {
			return pipeline.SeverityWarning, fmt.Sprintf("low resolution: %dx%d (min %dx%d)", w, h, minWidth, minHeight)
		}
	}

	// 4. Magic number — only when content-length suggests a small fetch is cheap.
	if resp.ContentLength > 0 && resp.ContentLength <= 1<<20 {
		if issue := v.checkMagic(ctx, url, ct); issue != "" {
			return pipeline.SeverityCritical, issue
		}
	}

	return pipeline.SeverityInfo, ""
}

// checkMagic fetches the first magicReadBytes of the resource and validates the magic number.
func (v *ImageQuality) checkMagic(ctx context.Context, url, ct string) string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("Range", fmt.Sprintf("bytes=0-%d", magicReadBytes-1))
	resp, err := v.client.Do(req)
	if err != nil {
		return "" // network issue — don't fail on magic check
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return ""
	}
	buf, err := io.ReadAll(io.LimitReader(resp.Body, int64(magicReadBytes)))
	if err != nil || len(buf) < 2 {
		return ""
	}

	sig, ok := magicSigs[ct]
	if !ok {
		return "" // avif and other types: skip magic check
	}
	if !bytes.HasPrefix(buf, sig) {
		return fmt.Sprintf("magic number mismatch for %s (got %x)", ct, buf[:min(4, len(buf))])
	}
	return ""
}

func parseDimHeader(h http.Header) (int, int) {
	w, _ := strconv.Atoi(h.Get("X-Image-Width"))
	ht, _ := strconv.Atoi(h.Get("X-Image-Height"))
	return w, ht
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
