// Package fingerprint implements sub-technique D.1 — HTML meta + header CMS
// fingerprinting.
//
// # What it does
//
// For each dealer_web_presence.domain, the fingerprinter fetches the homepage
// using a plain HTTP GET with the CardexBot user-agent (no JS rendering). It
// inspects:
//
//  1. HTTP response headers: X-Powered-By, X-Generator, Set-Cookie
//  2. HTML <meta name="generator"> content
//  3. Asset URL patterns in href/src attributes
//  4. Link relations (rel="https://api.w.org/" indicates WordPress REST API)
//  5. Body text patterns (wp-content, wp-includes, sites/default/files, etc.)
//
// # Output
//
// CMSResult is serialised as JSON and stored in
// dealer_web_presence.cms_fingerprint_json. The extraction pipeline (E01-E12)
// uses this field to choose the optimal extraction strategy per site.
//
// # CMS coverage
//
//   - WordPress  (all versions; version parsed from generator meta)
//   - Joomla     (3.x / 4.x / 5.x)
//   - Drupal     (7 / 8 / 9 / 10)
//   - Wix        (website builder)
//   - Squarespace (any version)
//   - Shopify    (e-commerce)
//   - Custom/Unknown (fallback)
//
// # Browser fallback
//
// D.1 uses plain HTTP only. Sites that require JS rendering for the <head> to
// be populated will score "unknown" with lower confidence. Browser-assisted
// re-scan is deferred to Sprint 13 (D.1b).
//
// BaseWeights["D"] = 0.0 -- D is capacity classification, not primary discovery.
package fingerprint

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
)

const (
	subTechID   = "D.1"
	subTechName = "HTML meta + header CMS fingerprinting"

	defaultTimeout  = 15 * time.Second
	maxBodyBytes    = 512 * 1024 // 512 KiB is enough to cover <head>
	cardexUA        = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// CMS identifies the detected content management system.
type CMS string

const (
	CMSWordPress   CMS = "wordpress"
	CMSJoomla      CMS = "joomla"
	CMSDrupal      CMS = "drupal"
	CMSWix         CMS = "wix"
	CMSSquarespace CMS = "squarespace"
	CMSShopify     CMS = "shopify"
	CMSCustom      CMS = "custom"
	CMSUnknown     CMS = "unknown"
)

// CMSResult is the output of D.1 for a single domain.
// It is serialised to JSON and stored in dealer_web_presence.cms_fingerprint_json.
type CMSResult struct {
	CMS        CMS      `json:"cms"`
	Version    string   `json:"version,omitempty"`  // e.g. "6.4.2" for WordPress
	Confidence float64  `json:"confidence"`          // 0.0-1.0
	Signals    []string `json:"signals,omitempty"`   // human-readable evidence list
	ScannedAt  string   `json:"scanned_at"`          // RFC3339 UTC
}

var reWPVersion = regexp.MustCompile(`(?i)WordPress\s+([\d.]+)`)
var reJoomlaVersion = regexp.MustCompile(`(?i)Joomla!\s*([\d.]+)`)
var reDrupalVersion = regexp.MustCompile(`(?i)Drupal\s+([\d.]+)`)

// Fingerprinter fetches and analyses a homepage to detect its CMS stack.
type Fingerprinter struct {
	client *http.Client
	log    *slog.Logger
}

// New returns a Fingerprinter with production HTTP settings.
func New() *Fingerprinter {
	return &Fingerprinter{
		client: &http.Client{
			Timeout: defaultTimeout,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				if len(via) >= 5 {
					return fmt.Errorf("too many redirects")
				}
				return nil
			},
		},
		log: slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient returns a Fingerprinter using the supplied HTTP client (for tests).
func NewWithClient(c *http.Client) *Fingerprinter {
	return &Fingerprinter{
		client: c,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (f *Fingerprinter) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (f *Fingerprinter) Name() string { return subTechName }

// FingerprintDomain fetches the homepage for domain and returns a CMSResult.
// domain should be a bare hostname (e.g. "example.de"). The fingerprinter
// tries HTTPS first, then falls back to HTTP.
func (f *Fingerprinter) FingerprintDomain(ctx context.Context, domain string) (*CMSResult, error) {
	resp, err := f.fetchHomepage(ctx, domain)
	if err != nil {
		return nil, fmt.Errorf("fingerprint %q: %w", domain, err)
	}
	defer resp.Body.Close()

	lr := io.LimitReader(resp.Body, maxBodyBytes)
	doc, err := goquery.NewDocumentFromReader(lr)
	if err != nil {
		return nil, fmt.Errorf("fingerprint %q: parse HTML: %w", domain, err)
	}

	return f.analyse(resp, doc), nil
}

// fetchHomepage tries HTTPS then HTTP.
func (f *Fingerprinter) fetchHomepage(ctx context.Context, domain string) (*http.Response, error) {
	for _, scheme := range []string{"https", "http"} {
		url := scheme + "://" + domain + "/"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			continue
		}
		req.Header.Set("User-Agent", cardexUA)
		req.Header.Set("Accept", "text/html,application/xhtml+xml")
		resp, err := f.client.Do(req)
		if err == nil {
			return resp, nil
		}
	}
	return nil, fmt.Errorf("unreachable over HTTPS and HTTP")
}

// analyse inspects headers and HTML to determine the CMS.
func (f *Fingerprinter) analyse(resp *http.Response, doc *goquery.Document) *CMSResult {
	var signals []string
	var cms CMS = CMSUnknown
	var version string
	var confidence float64

	headers := resp.Header

	// ---- WordPress ----------------------------------------------------------
	wpScore := 0

	// Generator meta
	generator := doc.Find(`meta[name="generator"]`).AttrOr("content", "")
	if strings.Contains(strings.ToLower(generator), "wordpress") {
		wpScore += 3
		signals = append(signals, "meta[generator]="+generator)
		if m := reWPVersion.FindStringSubmatch(generator); len(m) > 1 {
			version = m[1]
		}
	}

	// WordPress REST API link rel
	if doc.Find(`link[rel="https://api.w.org/"]`).Length() > 0 {
		wpScore += 3
		signals = append(signals, "link[rel=api.w.org]")
	}

	// Asset URL patterns
	bodyHTML, _ := doc.Html()
	if strings.Contains(bodyHTML, "/wp-content/") {
		wpScore += 2
		signals = append(signals, "asset:/wp-content/")
	}
	if strings.Contains(bodyHTML, "/wp-includes/") {
		wpScore += 2
		signals = append(signals, "asset:/wp-includes/")
	}

	// Cookies
	for _, cookie := range resp.Cookies() {
		if strings.HasPrefix(cookie.Name, "wordpress_") || strings.HasPrefix(cookie.Name, "wp-settings-") {
			wpScore += 2
			signals = append(signals, "cookie:"+cookie.Name)
		}
	}

	// X-Powered-By header
	xpb := headers.Get("X-Powered-By")
	if strings.Contains(strings.ToLower(xpb), "wordpress") {
		wpScore++
		signals = append(signals, "X-Powered-By:"+xpb)
	}

	if wpScore >= 2 {
		cms = CMSWordPress
		confidence = scoreToConfidence(wpScore, 10)
		return &CMSResult{CMS: cms, Version: version, Confidence: confidence,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Joomla --------------------------------------------------------------
	joomlaScore := 0

	if strings.Contains(strings.ToLower(generator), "joomla") {
		joomlaScore += 3
		signals = append(signals, "meta[generator]="+generator)
		if m := reJoomlaVersion.FindStringSubmatch(generator); len(m) > 1 {
			version = m[1]
		}
	}
	if strings.Contains(bodyHTML, "/components/com_") {
		joomlaScore += 2
		signals = append(signals, "asset:/components/com_")
	}
	if strings.Contains(bodyHTML, "/administrator/") {
		joomlaScore++
		signals = append(signals, "link:/administrator/")
	}
	for _, cookie := range resp.Cookies() {
		if cookie.Name == "joomla_user_state" || strings.Contains(cookie.Name, "joomla") {
			joomlaScore += 2
			signals = append(signals, "cookie:"+cookie.Name)
		}
	}

	if joomlaScore >= 2 {
		cms = CMSJoomla
		confidence = scoreToConfidence(joomlaScore, 8)
		return &CMSResult{CMS: cms, Version: version, Confidence: confidence,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Drupal --------------------------------------------------------------
	drupalScore := 0

	if strings.Contains(strings.ToLower(generator), "drupal") {
		drupalScore += 3
		signals = append(signals, "meta[generator]="+generator)
		if m := reDrupalVersion.FindStringSubmatch(generator); len(m) > 1 {
			version = m[1]
		}
	}
	xgen := headers.Get("X-Generator")
	if strings.Contains(strings.ToLower(xgen), "drupal") {
		drupalScore += 3
		signals = append(signals, "X-Generator:"+xgen)
	}
	if strings.Contains(bodyHTML, "/sites/default/files/") {
		drupalScore += 2
		signals = append(signals, "asset:/sites/default/files/")
	}
	if strings.Contains(bodyHTML, "/core/misc/drupal.js") || strings.Contains(bodyHTML, "Drupal.settings") {
		drupalScore += 2
		signals = append(signals, "drupal.js")
	}

	if drupalScore >= 2 {
		cms = CMSDrupal
		confidence = scoreToConfidence(drupalScore, 8)
		return &CMSResult{CMS: cms, Version: version, Confidence: confidence,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Wix ----------------------------------------------------------------
	if strings.Contains(bodyHTML, "wixstatic.com") || strings.Contains(bodyHTML, "static.wix.com") ||
		strings.Contains(bodyHTML, "wix-warmup-data") {
		signals = append(signals, "wixstatic.com CDN")
		return &CMSResult{CMS: CMSWix, Confidence: 0.92,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Squarespace --------------------------------------------------------
	if strings.Contains(bodyHTML, "static1.squarespace.com") || strings.Contains(bodyHTML, "squarespace-cdn.com") {
		signals = append(signals, "squarespace CDN")
		return &CMSResult{CMS: CMSSquarespace, Confidence: 0.92,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Shopify ------------------------------------------------------------
	if strings.Contains(strings.ToLower(xpb), "shopify") || strings.Contains(bodyHTML, "cdn.shopify.com") {
		signals = append(signals, "shopify CDN")
		return &CMSResult{CMS: CMSShopify, Confidence: 0.92,
			Signals: signals, ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	// ---- Custom / Unknown ---------------------------------------------------
	// If we got a 200 response the site is reachable but we couldn't fingerprint.
	if resp.StatusCode == http.StatusOK {
		return &CMSResult{CMS: CMSCustom, Confidence: 0.30,
			Signals: []string{"reachable-no-cms-signals"},
			ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	}

	return &CMSResult{CMS: CMSUnknown, Confidence: 0.10,
		Signals:   []string{fmt.Sprintf("http_%d", resp.StatusCode)},
		ScannedAt: time.Now().UTC().Format(time.RFC3339)}
}

// scoreToConfidence maps a raw signal score to [0, 1] clamped at the maximum
// expected score for this CMS type.
func scoreToConfidence(score, maxScore int) float64 {
	if score <= 0 {
		return 0.10
	}
	c := float64(score) / float64(maxScore)
	if c > 0.99 {
		c = 0.99
	}
	return c
}
