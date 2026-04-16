package e13_vlm_vision

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/extraction/internal/metrics"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E13"
	strategyName = "VLM Screenshot Vision"

	// PriorityE13 places E13 as the last automated strategy before E12 manual review.
	// E10 (email) = 200; E12 (manual) = 0; E13 sits between them.
	PriorityE13 = 100

	// maxImagesPerDealer caps the number of images sent to the VLM per dealer run.
	// On Hetzner CX42 with Phi-3.5 on CPU: ~45 s/image → 10 images ≈ 7.5 min.
	maxImagesPerDealer = 10

	// minImageSize skips images below this byte size (likely icons or spacers).
	minImageSize = 4 * 1024 // 4 KB

	// maxImageFetch is the HTTP timeout for downloading a single listing image.
	maxImageFetch = 15 * time.Second
)

// VLMExtractor implements pipeline.ExtractionStrategy for E13.
type VLMExtractor struct {
	client     VLMClient
	cfg        VLMConfig
	httpClient *http.Client
	log        *slog.Logger
}

// New creates a production VLMExtractor using the OllamaClient backend.
func New(cfg VLMConfig) *VLMExtractor {
	return NewWithClient(cfg,
		NewOllamaClient(cfg.Endpoint, cfg.Model, cfg.Timeout),
		&http.Client{Timeout: maxImageFetch},
	)
}

// NewWithClient creates a VLMExtractor with an injectable VLMClient.
// Use this constructor in tests (pass a MockClient) and for custom backends.
func NewWithClient(cfg VLMConfig, client VLMClient, httpClient *http.Client) *VLMExtractor {
	if httpClient == nil {
		httpClient = &http.Client{Timeout: maxImageFetch}
	}
	return &VLMExtractor{
		client:     client,
		cfg:        cfg,
		httpClient: httpClient,
		log:        slog.Default().With("strategy", strategyID),
	}
}

func (e *VLMExtractor) ID() string       { return strategyID }
func (e *VLMExtractor) Name() string     { return strategyName }
func (e *VLMExtractor) Priority() int    { return PriorityE13 }

// Applicable returns true for any dealer when VLM is enabled.
// VLM is opt-in (VLM_ENABLED=true) and acts as a universal last-resort fallback.
// Dealers with hint "vlm_required" or "screenshot_only" are prioritised via
// the Applicable check so they always reach E13 even if higher-priority
// strategies claim partial success.
func (e *VLMExtractor) Applicable(dealer pipeline.Dealer) bool {
	for _, hint := range dealer.ExtractionHints {
		if hint == "vlm_required" || hint == "screenshot_only" {
			return true
		}
	}
	// Universal fallback — applicable to all dealers (VLM_ENABLED guards instantiation).
	return true
}

// Extract fetches listing images from the dealer page and runs VLM inference on each.
//
// Flow:
//  1. Fetch dealer homepage HTML.
//  2. Extract candidate image URLs (listing photos, not icons).
//  3. For each image (up to maxImagesPerDealer): download, send to VLM, parse response.
//  4. Aggregate VehicleRaw results; mark extraction_method + AI Act metadata.
//  5. On timeout or all-error: set NextFallback = "E12".
func (e *VLMExtractor) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now().UTC(),
		SourceURL:   dealer.URLRoot,
	}
	e12 := "E12"
	result.NextFallback = &e12

	imageURLs, err := e.fetchListingImageURLs(ctx, dealer.URLRoot)
	if err != nil {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "HTTP_FETCH_ERROR",
			Message: err.Error(),
			URL:     dealer.URLRoot,
		})
		return result, nil
	}
	if len(imageURLs) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_IMAGES_FOUND",
			Message: "no candidate listing images found on dealer page",
			URL:     dealer.URLRoot,
		})
		return result, nil
	}

	if len(imageURLs) > maxImagesPerDealer {
		imageURLs = imageURLs[:maxImagesPerDealer]
	}

	result.SourceCount = len(imageURLs)
	var totalFields float64

	for _, imgURL := range imageURLs {
		if ctx.Err() != nil {
			break
		}

		imgData, err := e.downloadImage(ctx, imgURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "IMAGE_FETCH_ERROR",
				Message: err.Error(),
				URL:     imgURL,
			})
			metrics.E13Requests.WithLabelValues("error").Inc()
			continue
		}

		start := time.Now()
		inferCtx, cancel := context.WithTimeout(ctx, e.cfg.Timeout)
		raw, err := e.sendWithRetry(inferCtx, imgData)
		cancel()
		latency := time.Since(start).Seconds()
		metrics.E13Latency.Observe(latency)

		if err != nil {
			if ctx.Err() != nil || inferCtx.Err() != nil {
				metrics.E13Requests.WithLabelValues("timeout").Inc()
				result.Errors = append(result.Errors, pipeline.ExtractionError{
					Code:    "TIMEOUT",
					Message: fmt.Sprintf("VLM inference timed out after %.1fs: %v", latency, err),
					URL:     imgURL,
				})
			} else {
				metrics.E13Requests.WithLabelValues("error").Inc()
				result.Errors = append(result.Errors, pipeline.ExtractionError{
					Code:    "VLM_ERROR",
					Message: err.Error(),
					URL:     imgURL,
				})
			}
			continue
		}

		vehicle, fields := parseVLMResponse(raw)
		if vehicle == nil {
			metrics.E13Requests.WithLabelValues("error").Inc()
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "PARSE_ERROR",
				Message: "VLM response could not be parsed as vehicle JSON",
				URL:     imgURL,
			})
			continue
		}

		metrics.E13Requests.WithLabelValues("success").Inc()
		totalFields += float64(fields)

		// Tag every vehicle with E13 extraction metadata and AI Act disclosure.
		vehicle.AdditionalFields["extraction_method"] = "e13_vlm"
		vehicle.AdditionalFields["ai_generated"] = map[string]interface{}{
			"is_ai_generated": true,
			"model":           e.cfg.Model,
			"generated_at":    time.Now().UTC().Format(time.RFC3339),
		}
		vehicle.SourceURL = imgURL

		result.Vehicles = append(result.Vehicles, vehicle)
		e.log.Debug("VLM extracted vehicle",
			"dealer_id", dealer.ID,
			"img_url", imgURL,
			"fields", fields,
			"latency_s", latency,
		)
	}

	if len(result.Vehicles) > 0 {
		avgFields := totalFields / float64(len(result.Vehicles))
		metrics.E13FieldsExtracted.Set(avgFields)
		// Note: classifyResult (FullSuccess/PartialSuccess) is called by the orchestrator
		// after Extract returns, not by the strategy itself.
	}

	return result, nil
}

// sendWithRetry calls the VLM client up to cfg.MaxRetries times on transient errors.
func (e *VLMExtractor) sendWithRetry(ctx context.Context, image []byte) (string, error) {
	var lastErr error
	attempts := e.cfg.MaxRetries + 1
	if attempts < 1 {
		attempts = 1
	}
	for i := range attempts {
		if ctx.Err() != nil {
			return "", ctx.Err()
		}
		resp, err := e.client.SendImage(ctx, image, vlmPrompt)
		if err == nil {
			return resp, nil
		}
		lastErr = err
		if i < attempts-1 {
			e.log.Warn("VLM transient error, retrying",
				"attempt", i+1, "max", attempts, "err", err)
		}
	}
	return "", lastErr
}

// fetchListingImageURLs fetches the dealer homepage and returns candidate image URLs.
// Candidate images are those whose src path contains listing-related keywords or
// are large enough to be a vehicle photo (heuristic: exclude small icons).
func (e *VLMExtractor) fetchListingImageURLs(ctx context.Context, urlRoot string) ([]string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, urlRoot, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)")
	req.Header.Set("Accept", "text/html,application/xhtml+xml")

	resp, err := e.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch page: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusUnauthorized {
		return nil, fmt.Errorf("HTTP %d: access denied", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("parse HTML: %w", err)
	}

	seen := make(map[string]bool)
	var urls []string

	doc.Find("img").Each(func(_ int, sel *goquery.Selection) {
		src, ok := sel.Attr("src")
		if !ok || src == "" {
			// Try data-src (lazy-loaded images)
			src, ok = sel.Attr("data-src")
			if !ok || src == "" {
				return
			}
		}
		src = resolveURL(urlRoot, src)
		if src == "" || seen[src] {
			return
		}
		if !isListingImageURL(src) {
			return
		}
		seen[src] = true
		urls = append(urls, src)
	})

	return urls, nil
}

// downloadImage fetches image bytes from a URL; skips images below minImageSize.
func (e *VLMExtractor) downloadImage(ctx context.Context, imgURL string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, imgURL, nil)
	if err != nil {
		return nil, fmt.Errorf("build image request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)")

	resp, err := e.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("download image: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("image HTTP %d", resp.StatusCode)
	}

	data, err := io.ReadAll(io.LimitReader(resp.Body, 10*1024*1024)) // 10 MB cap
	if err != nil {
		return nil, fmt.Errorf("read image body: %w", err)
	}
	if len(data) < minImageSize {
		return nil, fmt.Errorf("image too small (%d bytes), likely an icon", len(data))
	}
	return data, nil
}

// isListingImageURL returns true when the URL path looks like a vehicle listing image
// rather than an icon, logo, or UI asset.
func isListingImageURL(u string) bool {
	lower := strings.ToLower(u)
	// Skip common non-listing image patterns.
	for _, skip := range []string{
		"icon", "logo", "sprite", "favicon", "avatar", "banner",
		"placeholder", "loading", "spinner", "blank", ".svg", ".gif",
	} {
		if strings.Contains(lower, skip) {
			return false
		}
	}
	// Accept only JPEG/PNG/WebP image URLs.
	for _, ext := range []string{".jpg", ".jpeg", ".png", ".webp"} {
		if strings.Contains(lower, ext) {
			return true
		}
	}
	// Accept URLs with listing-related path segments even without extension.
	for _, kw := range []string{
		"vehicle", "voiture", "auto", "car", "listing", "annonce",
		"occasion", "gebraucht", "used", "stock",
	} {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// resolveURL makes relative image src values absolute using the page base URL.
func resolveURL(base, src string) string {
	src = strings.TrimSpace(src)
	if src == "" || strings.HasPrefix(src, "data:") {
		return ""
	}
	if strings.HasPrefix(src, "http://") || strings.HasPrefix(src, "https://") {
		return src
	}
	base = strings.TrimRight(base, "/")
	if strings.HasPrefix(src, "/") {
		// Extract scheme+host from base.
		if idx := strings.Index(base, "://"); idx != -1 {
			rest := base[idx+3:]
			if slash := strings.IndexByte(rest, '/'); slash != -1 {
				return base[:idx+3] + rest[:slash] + src
			}
			return base + src
		}
		return base + src
	}
	return base + "/" + src
}
