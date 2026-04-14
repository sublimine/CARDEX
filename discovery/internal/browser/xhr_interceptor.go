package browser

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
)

// interceptXHR is the implementation backing Browser.InterceptXHR.
//
// It navigates to url in a fresh page, listens for all network responses using
// page.OnResponse, and collects those that match filter. Navigation waits for
// network idle so that all XHR/fetch calls triggered by page JS are captured.
//
// Typical use case: discovering the JSON API that a dealer-locator SPA calls
// so that subsequent requests can hit the API directly (without browser).
func (b *PlaywrightBrowser) interceptXHR(ctx context.Context, url string, filter XHRFilter) ([]*XHRCapture, error) {
	timeout := b.cfg.DefaultTimeout
	timeoutMs := float64(timeout.Milliseconds())

	host := ExtractHost(url)
	if b.rateLimiter != nil {
		if err := b.rateLimiter.Wait(host); err != nil {
			return nil, fmt.Errorf("browser.InterceptXHR: rate limit: %w", err)
		}
	}

	b.sem.acquire()
	defer b.sem.release()

	bctx, err := b.pool.acquire(host)
	if err != nil {
		return nil, fmt.Errorf("browser.InterceptXHR: context: %w", err)
	}

	page, err := bctx.NewPage()
	if err != nil {
		return nil, fmt.Errorf("browser.InterceptXHR: new page: %w", err)
	}
	defer func() {
		if closeErr := page.Close(); closeErr != nil {
			b.log.Warn("browser: xhr page close error", "url", url, "err", closeErr)
		}
	}()

	// Block visual resources — they're irrelevant for XHR discovery.
	if err := installResourceBlocker(page, DefaultBlockedResources); err != nil {
		return nil, fmt.Errorf("browser.InterceptXHR: resource blocker: %w", err)
	}

	// captures collects matching responses; mu protects it from the OnResponse callback.
	var (
		mu       sync.Mutex
		captures []*XHRCapture
	)

	// requestTimes records the start time of each request keyed by request ID
	// so we can compute per-request round-trip timing.
	requestTimes := make(map[string]time.Time)
	var rtMu sync.Mutex

	page.OnRequest(func(req playwright.Request) {
		rtMu.Lock()
		requestTimes[req.URL()] = time.Now()
		rtMu.Unlock()
	})

	page.OnResponse(func(resp playwright.Response) {
		status := resp.Status()
		respURL := resp.URL()
		method := resp.Request().Method()

		if !matchesFilter(respURL, method, status, filter) {
			return
		}

		capture := &XHRCapture{
			RequestURL:      respURL,
			RequestMethod:   method,
			RequestHeaders:  resp.Request().Headers(),
			ResponseStatus:  status,
			ResponseHeaders: resp.Headers(),
		}

		// Request body (available for POST/PUT).
		if rb, err := resp.Request().PostDataBuffer(); err == nil {
			capture.RequestBody = rb
		}

		// Response body — may fail for streaming or binary responses; non-fatal.
		if body, err := resp.Body(); err == nil {
			capture.ResponseBody = body
		}

		// Round-trip timing.
		rtMu.Lock()
		if startTime, ok := requestTimes[respURL]; ok {
			capture.Timing = time.Since(startTime)
		}
		rtMu.Unlock()

		mu.Lock()
		captures = append(captures, capture)
		mu.Unlock()
	})

	_, err = page.Goto(url, playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateNetworkidle,
		Timeout:   &timeoutMs,
	})
	if err != nil {
		return nil, fmt.Errorf("browser.InterceptXHR: goto %q: %w", url, err)
	}

	// Extra wait for lazy-loaded XHR that fire after network-idle.
	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State:   playwright.LoadStateNetworkidle,
		Timeout: &timeoutMs,
	}); err != nil {
		// Non-fatal — we already collected what we could.
		b.log.Warn("browser: interceptXHR: WaitForLoadState error", "url", url, "err", err)
	}

	// Check context cancellation.
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	mu.Lock()
	result := make([]*XHRCapture, len(captures))
	copy(result, captures)
	mu.Unlock()

	b.log.Debug("browser: InterceptXHR done",
		"url", url, "captured", len(result))
	return result, nil
}
