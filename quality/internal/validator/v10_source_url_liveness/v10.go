// Package v10_source_url_liveness implements validation strategy V10 — Source URL Liveness.
//
// # Strategy
//
// The source URL is the canonical listing page from which the vehicle was
// extracted. A vehicle whose listing is no longer live should be flagged for
// removal from the catalogue.
//
// # HTTP status rules
//
//   - 200           → PASS (listing is live)
//   - 301/302       → INFO (redirected — still alive, but URL may need update)
//   - 404/410       → CRITICAL (listing removed or permanently gone)
//   - 5xx           → WARNING (server error — retry later)
//   - request error → WARNING (network/DNS issue — transient)
//   - timeout       → WARNING
//
// # Caching
//
// Results are cached in an in-memory map (TTL = 24 h by default) so that bulk
// validation runs do not hammer source sites. A SQLite-backed cache is deferred
// to Phase 5.
package v10_source_url_liveness

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V10"
	strategyName = "Source URL Liveness"

	defaultCacheTTL = 24 * time.Hour
	defaultTimeout  = 10 * time.Second
)

type cacheEntry struct {
	status   int
	checkedAt time.Time
}

// LivenessChecker implements pipeline.Validator for V10.
type LivenessChecker struct {
	client   *http.Client
	cacheTTL time.Duration
	mu       sync.Mutex
	cache    map[string]*cacheEntry
}

// New returns a LivenessChecker with defaults.
func New() *LivenessChecker {
	return NewWithClient(
		&http.Client{
			Timeout: defaultTimeout,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse // capture redirect, don't follow
			},
		},
		defaultCacheTTL,
	)
}

// NewWithClient returns a LivenessChecker with a custom HTTP client and cache TTL.
func NewWithClient(c *http.Client, cacheTTL time.Duration) *LivenessChecker {
	return &LivenessChecker{
		client:   c,
		cacheTTL: cacheTTL,
		cache:    make(map[string]*cacheEntry),
	}
}

func (v *LivenessChecker) ID() string                 { return strategyID }
func (v *LivenessChecker) Name() string               { return strategyName }
func (v *LivenessChecker) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks whether vehicle.SourceURL responds to a HEAD request.
func (v *LivenessChecker) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	url := strings.TrimSpace(vehicle.SourceURL)
	if url == "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no source URL to check"
		result.Confidence = 1.0
		return result, nil
	}

	result.Evidence["source_url"] = url

	status, fromCache := v.probe(ctx, url)
	result.Evidence["http_status"] = fmt.Sprintf("%d", status)
	if fromCache {
		result.Evidence["from_cache"] = "true"
	}

	switch {
	case status == http.StatusOK:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 1.0

	case status == http.StatusMovedPermanently || status == http.StatusFound ||
		status == http.StatusTemporaryRedirect || status == http.StatusPermanentRedirect:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("listing redirects (HTTP %d) — URL may need update", status)
		result.Confidence = 0.9

	case status == http.StatusNotFound:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "listing removed — HTTP 404 (vehicle no longer available)"
		result.Confidence = 0.95
		result.Suggested["action"] = "remove or archive this vehicle listing"

	case status == http.StatusGone:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "listing permanently removed — HTTP 410"
		result.Confidence = 1.0
		result.Suggested["action"] = "remove this vehicle listing"

	case status >= 500:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("source server error HTTP %d — retry later", status)
		result.Confidence = 0.6

	case status == -1:
		// Network error or timeout.
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = "source URL unreachable — network error or timeout"
		result.Confidence = 0.5

	default:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("unexpected HTTP %d", status)
		result.Confidence = 0.7
	}
	return result, nil
}

// probe performs a cached HEAD request and returns the HTTP status code.
// Returns -1 on network error or timeout. fromCache indicates a cache hit.
func (v *LivenessChecker) probe(ctx context.Context, url string) (status int, fromCache bool) {
	v.mu.Lock()
	if e, ok := v.cache[url]; ok && time.Since(e.checkedAt) < v.cacheTTL {
		v.mu.Unlock()
		return e.status, true
	}
	v.mu.Unlock()

	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return -1, false
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot)")

	resp, err := v.client.Do(req)
	if err != nil {
		v.storeCache(url, -1)
		return -1, false
	}
	defer resp.Body.Close()

	v.storeCache(url, resp.StatusCode)
	return resp.StatusCode, false
}

func (v *LivenessChecker) storeCache(url string, status int) {
	v.mu.Lock()
	v.cache[url] = &cacheEntry{status: status, checkedAt: time.Now()}
	v.mu.Unlock()
}
