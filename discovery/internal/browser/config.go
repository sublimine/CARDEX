// Package browser provides a transparent headless browser for legitimate
// rendering of JavaScript-heavy sites. CARDEX policy mandates:
//
//  1. Identifiable User-Agent: "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
//  2. Respect for robots.txt (checked by caller before invoking this package).
//  3. Respect for site-declared rate limits (HostRateLimiter enforces minimum gaps).
//  4. NO stealth plugins (playwright-stealth, undetected-chromedriver, puppeteer-extra).
//  5. NO TLS fingerprint spoofing (JA3/JA4).
//  6. NO residential proxy evasion.
//  7. NO anti-detection bypass techniques of any kind.
//
// This module exists solely to render JavaScript-rendered public content that
// static HTTP fetchers cannot access. It is NOT a tool for evasion.
//
// Any PR introducing the banned techniques listed above is blocked by CI
// (illegal-pattern-scan.yml, rule CS-0-1).
package browser

import (
	"time"

	"cardex.eu/discovery/internal/ua"
)

// ResourceType classifies a browser resource that can be blocked for efficiency.
type ResourceType string

const (
	ResourceTypeImage    ResourceType = "image"
	ResourceTypeFont     ResourceType = "font"
	ResourceTypeMedia    ResourceType = "media"
	ResourceTypeStylesheet ResourceType = "stylesheet"
	ResourceTypeOther    ResourceType = "other"
)

// DefaultBlockedResources is the default set of resources to abort — types that
// are never needed to render text content and only waste bandwidth on a VPS.
var DefaultBlockedResources = []ResourceType{
	ResourceTypeImage,
	ResourceTypeFont,
	ResourceTypeMedia,
}

// BrowserConfig holds all configuration for the PlaywrightBrowser.
type BrowserConfig struct {
	// UserAgent is the HTTP User-Agent. MUST start with "CardexBot/" per policy.
	// Default: cardexUA constant below.
	UserAgent string

	// Headless controls whether Chromium runs headlessly. Default: true.
	Headless bool

	// ViewportWidth and ViewportHeight. Default: 1920 × 1080.
	ViewportWidth  int
	ViewportHeight int

	// Locale for navigator.language. Default: "en-US".
	Locale string

	// TimezoneID for JS Date. Default: "UTC".
	TimezoneID string

	// ExtraHeaders are sent with every request made by any page using this browser.
	ExtraHeaders map[string]string

	// MaxConcurrentPages limits simultaneously open pages. Default: 3.
	MaxConcurrentPages int

	// DefaultTimeout is the fallback timeout for navigation + waits. Default: 30s.
	DefaultTimeout time.Duration

	// MinIntervalPerHost is the minimum gap between requests to the same host.
	// Default: 5s.
	MinIntervalPerHost time.Duration

	// ChromiumArgs are passed verbatim to Chromium launch. The defaults cover
	// no-sandbox (container-friendly) and GPU-less operation.
	ChromiumArgs []string
}

// cardexUA is the canonical CARDEX bot User-Agent. Sourced from ua.CardexUA.
const cardexUA = ua.CardexUA

// DefaultBrowserConfig returns a BrowserConfig with all CARDEX policy defaults.
func DefaultBrowserConfig() *BrowserConfig {
	return &BrowserConfig{
		UserAgent:      cardexUA,
		Headless:       true,
		ViewportWidth:  1920,
		ViewportHeight: 1080,
		Locale:         "en-US",
		TimezoneID:     "UTC",
		ExtraHeaders: map[string]string{
			"X-Robots-Id": "cardex-bot-v1",
			"From":        "bot@cardex.eu",
		},
		MaxConcurrentPages: 3,
		DefaultTimeout:     30 * time.Second,
		MinIntervalPerHost: 5 * time.Second,
		ChromiumArgs: []string{
			"--no-sandbox",
			"--disable-dev-shm-usage",
			"--disable-gpu",
			"--disable-software-rasterizer",
		},
	}
}

// FetchOptions controls the behaviour of Browser.FetchHTML.
type FetchOptions struct {
	// WaitForNetworkIdle waits for the networkidle load state before returning.
	// Default: true.
	WaitForNetworkIdle bool

	// WaitForSelector waits for a specific CSS selector to appear before
	// returning HTML. Empty string means no selector wait. Applied after
	// WaitForNetworkIdle.
	WaitForSelector string

	// Timeout overrides DefaultBrowserConfig.DefaultTimeout for this call.
	// Zero means use the default.
	Timeout time.Duration

	// BlockResources overrides the default resource blocking list for this call.
	// Nil means use DefaultBlockedResources.
	BlockResources []ResourceType

	// Headers are extra per-request headers (merged with ExtraHeaders in config).
	Headers map[string]string
}

// FetchResult is the output of Browser.FetchHTML.
type FetchResult struct {
	// URL is the originally requested URL.
	URL string

	// StatusCode is the HTTP status of the final navigation response.
	StatusCode int

	// HTML is the serialised DOM at the point of extraction.
	HTML string

	// FinalURL is the URL after all redirects.
	FinalURL string

	// Cookies is the browser cookie jar after page load.
	Cookies []Cookie

	// LoadDuration is the wall-clock time from Goto start to content extracted.
	LoadDuration time.Duration
}

// Cookie mirrors a browser cookie.
type Cookie struct {
	Name   string
	Value  string
	Domain string
	Path   string
}

// ScreenshotOptions controls the behaviour of Browser.Screenshot.
type ScreenshotOptions struct {
	// FullPage captures the entire scrollable page. Default: true.
	FullPage bool

	// ClipSelector captures only the element matching this CSS selector.
	// Empty string means full-page or viewport.
	ClipSelector string

	// Format is "png" (lossless, default) or "jpeg".
	Format string

	// Quality is the JPEG quality (1-100). Ignored for PNG.
	Quality int

	// Timeout overrides the default timeout for this call.
	Timeout time.Duration
}

// ScreenshotResult is the output of Browser.Screenshot.
type ScreenshotResult struct {
	// URL is the originally requested URL.
	URL string

	// ImageBytes is the raw image data.
	ImageBytes []byte

	// Format is "png" or "jpeg".
	Format string

	// Width and Height of the image in pixels.
	Width, Height int

	// CapturedAt is the wall-clock timestamp of capture.
	CapturedAt time.Time
}

// XHRFilter restricts which XHR/fetch responses are captured by InterceptXHR.
type XHRFilter struct {
	// URLPattern is a substring or regex pattern matched against the response URL.
	// Empty string matches all URLs.
	URLPattern string

	// MethodFilter restricts to specific HTTP methods (e.g. ["GET", "POST"]).
	// Empty slice matches all methods.
	MethodFilter []string

	// MinStatusCode ignores responses with status below this value. Default: 0 (all).
	MinStatusCode int
}

// XHRCapture is a single captured XHR/fetch request-response pair.
type XHRCapture struct {
	// RequestURL is the full URL of the captured request.
	RequestURL string

	// RequestMethod is the HTTP method (GET, POST, etc.).
	RequestMethod string

	// RequestHeaders are the outgoing request headers.
	RequestHeaders map[string]string

	// RequestBody is the POST body, if any.
	RequestBody []byte

	// ResponseStatus is the HTTP status code.
	ResponseStatus int

	// ResponseHeaders are the response headers.
	ResponseHeaders map[string]string

	// ResponseBody is the raw response body.
	ResponseBody []byte

	// Timing is the round-trip duration of the XHR request.
	Timing time.Duration
}
