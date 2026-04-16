package browser

import (
	"fmt"
	"math"
	"math/rand/v2"
	"net/http"
	"strconv"
	"time"
)

// RetryTransport wraps an http.RoundTripper with exponential backoff + jitter.
//
// Retries on:
//   - 429 Too Many Requests (also respects Retry-After header)
//   - 503 Service Unavailable
//   - connection / transport-level errors (nil response)
//
// Does NOT retry:
//   - 4xx client errors (except 429)
//   - 5xx server errors (except 503)
//
// The delay formula for attempt n (0-indexed) is:
//
//	delay = min(BaseDelay*2^n + rand(0, BaseDelay), MaxDelay)
type RetryTransport struct {
	Base       http.RoundTripper // underlying transport; defaults to http.DefaultTransport
	MaxRetries int               // default 3
	BaseDelay  time.Duration     // default 1s
	MaxDelay   time.Duration     // default 30s

	// nowFn is injectable for testing; defaults to time.Now.
	nowFn func() time.Time
	// sleepFn is injectable for testing; defaults to time.Sleep.
	sleepFn func(time.Duration)
}

// defaultRetryTransport returns a RetryTransport with production defaults.
func defaultRetryTransport() *RetryTransport {
	return &RetryTransport{
		Base:       http.DefaultTransport,
		MaxRetries: 3,
		BaseDelay:  1 * time.Second,
		MaxDelay:   30 * time.Second,
	}
}

func (rt *RetryTransport) base() http.RoundTripper {
	if rt.Base != nil {
		return rt.Base
	}
	return http.DefaultTransport
}

func (rt *RetryTransport) maxRetries() int {
	if rt.MaxRetries > 0 {
		return rt.MaxRetries
	}
	return 3
}

func (rt *RetryTransport) baseDelay() time.Duration {
	if rt.BaseDelay > 0 {
		return rt.BaseDelay
	}
	return 1 * time.Second
}

func (rt *RetryTransport) maxDelay() time.Duration {
	if rt.MaxDelay > 0 {
		return rt.MaxDelay
	}
	return 30 * time.Second
}

func (rt *RetryTransport) sleep(d time.Duration) {
	if rt.sleepFn != nil {
		rt.sleepFn(d)
		return
	}
	time.Sleep(d)
}

// RoundTrip executes the request with exponential backoff retry logic.
func (rt *RetryTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	maxRetries := rt.maxRetries()

	var (
		resp    *http.Response
		lastErr error
	)

	for attempt := 0; attempt <= maxRetries; attempt++ {
		// Clone the request body for each retry (body was already read on
		// attempt 0; subsequent attempts get a fresh clone from GetBody if set).
		r := req
		if attempt > 0 && req.GetBody != nil {
			body, err := req.GetBody()
			if err != nil {
				return nil, fmt.Errorf("retry: clone request body: %w", err)
			}
			r = req.Clone(req.Context())
			r.Body = body
		}

		resp, lastErr = rt.base().RoundTrip(r)

		if lastErr == nil && !shouldRetry(resp.StatusCode) {
			// Success or a non-retryable status — return immediately.
			return resp, nil
		}

		if attempt == maxRetries {
			break
		}

		// Close response body before retry to avoid resource leaks.
		if resp != nil {
			_ = resp.Body.Close()
		}

		delay := rt.retryDelay(attempt, resp)
		rt.sleep(delay)
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return resp, nil
}

// shouldRetry reports whether a response with status code s should trigger a retry.
func shouldRetry(status int) bool {
	return status == http.StatusTooManyRequests || status == http.StatusServiceUnavailable
}

// retryDelay computes the backoff delay for the given attempt (0-indexed).
// If resp is a 429 with a Retry-After header, that duration is honoured
// (capped at MaxDelay).
func (rt *RetryTransport) retryDelay(attempt int, resp *http.Response) time.Duration {
	if resp != nil && resp.StatusCode == http.StatusTooManyRequests {
		if ra := resp.Header.Get("Retry-After"); ra != "" {
			if d := parseRetryAfter(ra, rt.nowFn); d > 0 {
				if d > rt.maxDelay() {
					return rt.maxDelay()
				}
				return d
			}
		}
	}

	base := rt.baseDelay()
	exp := time.Duration(math.Pow(2, float64(attempt))) * base
	jitter := time.Duration(rand.Float64() * float64(base))
	delay := exp + jitter
	if delay > rt.maxDelay() {
		delay = rt.maxDelay()
	}
	return delay
}

// parseRetryAfter parses a Retry-After header value, which may be either a
// delta-seconds integer or an HTTP-date string.
func parseRetryAfter(value string, nowFn func() time.Time) time.Duration {
	// Try delta-seconds first.
	if secs, err := strconv.ParseFloat(value, 64); err == nil && secs >= 0 {
		return time.Duration(secs * float64(time.Second))
	}
	// Try HTTP-date.
	t, err := http.ParseTime(value)
	if err != nil {
		return 0
	}
	now := time.Now()
	if nowFn != nil {
		now = nowFn()
	}
	d := t.Sub(now)
	if d < 0 {
		return 0
	}
	return d
}
