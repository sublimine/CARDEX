package browser

import (
	"context"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"bytes"
	"time"

	"github.com/playwright-community/playwright-go"
)

// screenshot is the implementation backing Browser.Screenshot.
//
// It renders the page fully (networkidle) and captures a PNG or JPEG image.
// Intended as the primary input to VLM extraction (Innovation #2 — E13 strategy):
//
//	E13: Screenshot() → ONNX Phi-3.5 Vision / LLaVA-CoT → structured JSON extraction
//
// For full-page screenshots of dealer sites without Schema.org markup, this
// method provides a reliable fallback to static HTML parsing.
func (b *PlaywrightBrowser) screenshot(ctx context.Context, url string, opts *ScreenshotOptions) (*ScreenshotResult, error) {
	if opts == nil {
		opts = &ScreenshotOptions{
			FullPage: true,
			Format:   "png",
		}
	}
	if opts.Format == "" {
		opts.Format = "png"
	}

	timeout := b.cfg.DefaultTimeout
	if opts.Timeout > 0 {
		timeout = opts.Timeout
	}
	timeoutMs := float64(timeout.Milliseconds())

	host := ExtractHost(url)
	if b.rateLimiter != nil {
		if err := b.rateLimiter.Wait(host); err != nil {
			return nil, fmt.Errorf("browser.Screenshot: rate limit: %w", err)
		}
	}

	b.sem.acquire()
	defer b.sem.release()

	bctx, err := b.pool.acquire(host)
	if err != nil {
		return nil, fmt.Errorf("browser.Screenshot: context: %w", err)
	}

	page, err := bctx.NewPage()
	if err != nil {
		return nil, fmt.Errorf("browser.Screenshot: new page: %w", err)
	}
	defer func() {
		if closeErr := page.Close(); closeErr != nil {
			b.log.Warn("browser: screenshot page close error", "url", url, "err", closeErr)
		}
	}()

	// For screenshots we allow images through — they may be part of vehicle photos
	// needed for VLM analysis. Block only fonts and media.
	if err := installResourceBlocker(page, []ResourceType{ResourceTypeFont, ResourceTypeMedia}); err != nil {
		return nil, fmt.Errorf("browser.Screenshot: resource blocker: %w", err)
	}

	_, err = page.Goto(url, playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateNetworkidle,
		Timeout:   &timeoutMs,
	})
	if err != nil {
		return nil, fmt.Errorf("browser.Screenshot: goto %q: %w", url, err)
	}

	// Check context cancellation before the (potentially slow) screenshot call.
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	captureOpts := playwright.PageScreenshotOptions{
		FullPage: playwright.Bool(opts.FullPage),
	}

	switch opts.Format {
	case "jpeg", "jpg":
		captureOpts.Type = playwright.ScreenshotTypeJpeg
		if opts.Quality > 0 {
			q := opts.Quality
			captureOpts.Quality = &q
		}
	default:
		captureOpts.Type = playwright.ScreenshotTypePng
	}

	// If ClipSelector is set, scroll the element into view and clip to it.
	if opts.ClipSelector != "" {
		el, err := page.WaitForSelector(opts.ClipSelector,
			playwright.PageWaitForSelectorOptions{Timeout: &timeoutMs})
		if err != nil {
			return nil, fmt.Errorf("browser.Screenshot: wait for selector %q: %w",
				opts.ClipSelector, err)
		}
		box, err := el.BoundingBox()
		if err != nil {
			return nil, fmt.Errorf("browser.Screenshot: bounding box: %w", err)
		}
		if box != nil {
			captureOpts.FullPage = playwright.Bool(false)
			captureOpts.Clip = &playwright.Rect{
				X:      box.X,
				Y:      box.Y,
				Width:  box.Width,
				Height: box.Height,
			}
		}
	}

	imgBytes, err := page.Screenshot(captureOpts)
	if err != nil {
		return nil, fmt.Errorf("browser.Screenshot: capture: %w", err)
	}

	w, h := imageDimensions(imgBytes, opts.Format)

	result := &ScreenshotResult{
		URL:        url,
		ImageBytes: imgBytes,
		Format:     opts.Format,
		Width:      w,
		Height:     h,
		CapturedAt: time.Now(),
	}

	b.log.Debug("browser: Screenshot done",
		"url", url, "format", opts.Format, "bytes", len(imgBytes),
		"width", w, "height", h)
	return result, nil
}

// imageDimensions decodes the first few bytes of an image to extract
// width and height. Returns (0, 0) on failure.
func imageDimensions(data []byte, format string) (w, h int) {
	r := bytes.NewReader(data)
	var img image.Image
	var err error
	switch format {
	case "jpeg", "jpg":
		img, err = jpeg.Decode(r)
	default:
		img, err = png.Decode(r)
	}
	if err != nil {
		return 0, 0
	}
	bounds := img.Bounds()
	return bounds.Max.X - bounds.Min.X, bounds.Max.Y - bounds.Min.Y
}
