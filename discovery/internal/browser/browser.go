package browser

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"time"

	"github.com/playwright-community/playwright-go"
)

// Browser is the public interface for the headless browser module.
//
// All methods respect CARDEX transparency policy: CardexBot UA, no evasion,
// robots.txt compliance is the caller's responsibility.
type Browser interface {
	// FetchHTML navigates to url, waits for the page to settle, and returns the
	// rendered HTML. Respects rate limiting per host.
	FetchHTML(ctx context.Context, url string, opts *FetchOptions) (*FetchResult, error)

	// Screenshot navigates to url and captures a screenshot of the rendered page.
	// Useful as input to VLM extraction (Innovation #2 — E13 strategy).
	Screenshot(ctx context.Context, url string, opts *ScreenshotOptions) (*ScreenshotResult, error)

	// InterceptXHR navigates to url, captures all XHR/fetch responses that match
	// filter, and returns them. Useful for discovering hidden JSON APIs used by
	// dealer-locator SPAs.
	InterceptXHR(ctx context.Context, url string, filter XHRFilter) ([]*XHRCapture, error)

	// Close shuts down the browser gracefully, releasing all contexts and the
	// underlying Playwright instance.
	Close() error
}

// PlaywrightBrowser implements Browser using playwright-community/playwright-go.
type PlaywrightBrowser struct {
	pw          *playwright.Playwright
	browser     playwright.Browser
	pool        *contextPool
	sem         *pageSemaphore
	rateLimiter *HostRateLimiter
	cfg         *BrowserConfig
	log         *slog.Logger
}

// New initialises Playwright, launches Chromium headlessly, and returns a ready
// PlaywrightBrowser. Callers must call Close() when done.
//
// db is used for HostRateLimiter persistence. Pass nil to skip rate-limit
// persistence (uses in-process memory only, lost on restart).
func New(cfg *BrowserConfig, db *sql.DB) (*PlaywrightBrowser, error) {
	if cfg == nil {
		cfg = DefaultBrowserConfig()
	}

	pw, err := playwright.Run()
	if err != nil {
		return nil, fmt.Errorf("browser.New: playwright.Run: %w", err)
	}

	timeout := float64(cfg.DefaultTimeout.Milliseconds())
	b, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(cfg.Headless),
		Args:     cfg.ChromiumArgs,
		Timeout:  &timeout,
	})
	if err != nil {
		_ = pw.Stop()
		return nil, fmt.Errorf("browser.New: launch Chromium: %w", err)
	}

	var rl *HostRateLimiter
	if db != nil {
		rl, err = NewHostRateLimiter(db, cfg.MinIntervalPerHost)
		if err != nil {
			_ = b.Close()
			_ = pw.Stop()
			return nil, fmt.Errorf("browser.New: rate limiter: %w", err)
		}
	}

	return &PlaywrightBrowser{
		pw:          pw,
		browser:     b,
		pool:        newContextPool(b, cfg),
		sem:         newPageSemaphore(cfg.MaxConcurrentPages),
		rateLimiter: rl,
		cfg:         cfg,
		log:         slog.Default().With("component", "browser"),
	}, nil
}

// Close gracefully shuts down all contexts, the browser, and the Playwright
// driver process.
func (b *PlaywrightBrowser) Close() error {
	b.pool.closeAll()
	if err := b.browser.Close(); err != nil {
		b.log.Warn("browser: browser close error", "err", err)
	}
	if err := b.pw.Stop(); err != nil {
		return fmt.Errorf("browser.Close: playwright stop: %w", err)
	}
	return nil
}

// FetchHTML navigates to url and returns the rendered HTML.
func (b *PlaywrightBrowser) FetchHTML(ctx context.Context, url string, opts *FetchOptions) (*FetchResult, error) {
	if opts == nil {
		opts = &FetchOptions{WaitForNetworkIdle: true}
	}
	timeout := b.cfg.DefaultTimeout
	if opts.Timeout > 0 {
		timeout = opts.Timeout
	}

	host := ExtractHost(url)
	if b.rateLimiter != nil {
		if err := b.rateLimiter.Wait(host); err != nil {
			return nil, fmt.Errorf("browser.FetchHTML: rate limit: %w", err)
		}
	}

	b.sem.acquire()
	defer b.sem.release()

	bctx, err := b.pool.acquire(host)
	if err != nil {
		return nil, fmt.Errorf("browser.FetchHTML: context: %w", err)
	}

	page, err := bctx.NewPage()
	if err != nil {
		return nil, fmt.Errorf("browser.FetchHTML: new page: %w", err)
	}
	defer func() {
		if closeErr := page.Close(); closeErr != nil {
			b.log.Warn("browser: page close error", "url", url, "err", closeErr)
		}
	}()

	// Apply extra per-call headers.
	if len(opts.Headers) > 0 {
		if err := page.SetExtraHTTPHeaders(opts.Headers); err != nil {
			return nil, fmt.Errorf("browser.FetchHTML: set headers: %w", err)
		}
	}

	// Block unwanted resource types.
	blocked := opts.BlockResources
	if blocked == nil {
		blocked = DefaultBlockedResources
	}
	if err := installResourceBlocker(page, blocked); err != nil {
		return nil, fmt.Errorf("browser.FetchHTML: resource blocker: %w", err)
	}

	start := time.Now()
	timeoutMs := float64(timeout.Milliseconds())

	var waitUntil *playwright.WaitUntilState
	if opts.WaitForNetworkIdle {
		waitUntil = playwright.WaitUntilStateNetworkidle
	} else {
		waitUntil = playwright.WaitUntilStateLoad
	}

	resp, err := page.Goto(url, playwright.PageGotoOptions{
		WaitUntil: waitUntil,
		Timeout:   &timeoutMs,
	})
	if err != nil {
		return nil, fmt.Errorf("browser.FetchHTML: goto %q: %w", url, err)
	}

	// Optionally wait for a specific element to appear.
	if opts.WaitForSelector != "" {
		if _, err := page.WaitForSelector(opts.WaitForSelector,
			playwright.PageWaitForSelectorOptions{Timeout: &timeoutMs}); err != nil {
			return nil, fmt.Errorf("browser.FetchHTML: wait for selector %q: %w",
				opts.WaitForSelector, err)
		}
	}

	html, err := page.Content()
	if err != nil {
		return nil, fmt.Errorf("browser.FetchHTML: content: %w", err)
	}

	duration := time.Since(start)
	result := &FetchResult{
		URL:          url,
		HTML:         html,
		LoadDuration: duration,
		FinalURL:     page.URL(),
	}
	if resp != nil {
		result.StatusCode = resp.Status()
	}

	b.log.Debug("browser: FetchHTML done",
		"url", url, "status", result.StatusCode, "duration_ms", duration.Milliseconds())
	return result, nil
}

// ── Resource blocking ─────────────────────────────────────────────────────────

// resourceTypePatterns maps ResourceType to URL glob patterns that Playwright
// uses to identify them. We abort these before they consume bandwidth.
var resourceTypePatterns = map[ResourceType][]string{
	ResourceTypeImage: {
		"**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif",
		"**/*.webp", "**/*.ico", "**/*.svg", "**/*.avif",
	},
	ResourceTypeFont: {
		"**/*.woff", "**/*.woff2", "**/*.ttf", "**/*.eot", "**/*.otf",
	},
	ResourceTypeMedia: {
		"**/*.mp4", "**/*.webm", "**/*.ogg", "**/*.mp3", "**/*.wav",
		"**/*.avi", "**/*.mov",
	},
}

// installResourceBlocker registers route handlers on page to abort the
// resource types listed in blocked.
func installResourceBlocker(page playwright.Page, blocked []ResourceType) error {
	patterns := make(map[string]bool)
	for _, rt := range blocked {
		for _, p := range resourceTypePatterns[rt] {
			patterns[p] = true
		}
	}
	for pattern := range patterns {
		p := pattern // capture for closure
		if err := page.Route(p, func(route playwright.Route) {
			_ = route.Abort()
		}); err != nil {
			return fmt.Errorf("installResourceBlocker: route %q: %w", p, err)
		}
	}
	return nil
}

// ── XHR interception (wired in xhr_interceptor.go) ───────────────────────────

// InterceptXHR navigates to url and returns all XHR/fetch responses matching filter.
func (b *PlaywrightBrowser) InterceptXHR(ctx context.Context, url string, filter XHRFilter) ([]*XHRCapture, error) {
	return b.interceptXHR(ctx, url, filter)
}

// ── Screenshot (wired in screenshot.go) ──────────────────────────────────────

// Screenshot navigates to url and captures a screenshot.
func (b *PlaywrightBrowser) Screenshot(ctx context.Context, url string, opts *ScreenshotOptions) (*ScreenshotResult, error) {
	return b.screenshot(ctx, url, opts)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// matchesFilter checks whether a captured response/request pair satisfies XHRFilter.
func matchesFilter(captureURL, method string, status int, filter XHRFilter) bool {
	if filter.MinStatusCode > 0 && status < filter.MinStatusCode {
		return false
	}
	if len(filter.MethodFilter) > 0 {
		found := false
		for _, m := range filter.MethodFilter {
			if strings.EqualFold(m, method) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	if filter.URLPattern != "" {
		matched, _ := regexp.MatchString(filter.URLPattern, captureURL)
		if !matched {
			return false
		}
	}
	return true
}
