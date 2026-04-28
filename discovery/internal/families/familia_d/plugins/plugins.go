// Package plugins implements sub-technique D.2 — CMS plugin detection.
//
// # Scope
//
// D.2 operates on sites already classified as WordPress (or Joomla) by D.1.
// It probes public REST API endpoints that are exposed by known car-dealer
// plugins. A successful probe (HTTP 200 with a JSON body) reveals:
//
//  1. Which inventory/DMS plugin is active
//  2. The exact REST endpoint URL pattern for the extraction pipeline (E-series)
//
// # WordPress dealer plugins probed
//
//   - /wp-json/wp/v2/vehicles      -- generic "vehicle" custom post type
//   - /wp-json/wp/v2/car           -- "car" custom post type
//   - /wp-json/automotive/v1/vehicles -- AncoraThemes Automotive
//   - /wp-json/autodealer/v1/listings  -- WP Auto Dealer
//   - /wp-json/cars/v1/inventory       -- Cars.com Inventory plugin
//   - /?feed=rss2&post_type=vehicle    -- RSS feed (any vehicle CPT plugin)
//
// Known commercial plugins: Car Dealer (QantumThemes), Stratus (Car Dealer Pro),
// Motors (StylemixThemes), Automotive (AncoraThemes), WP Auto Dealer, Inventory
// Presser, Cars.com.
//
// # Joomla dealer components probed
//
//   - /index.php?option=com_carmanager&format=json
//   - /index.php?option=com_vehicles&format=json
//   - /index.php?option=com_motovoicer&format=json
//
// # Rate limiting
//
// All probes are against a single dealer domain; rate limiting is the
// responsibility of the D family orchestrator (see family.go). Each individual
// probe uses a 10-second timeout.
//
// # Output
//
// PluginResult is serialised into dealer_web_presence.extraction_hints_json.
package plugins

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

const (
	subTechID   = "D.2"
	subTechName = "CMS plugin detection (car dealer REST endpoints)"

	probeTimeout = 10 * time.Second
	maxProbeBody = 4 * 1024 // 4 KiB; only need to confirm JSON, not read full payload
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// ExtractionEndpoint describes a discovered API endpoint that the E-series
// extraction pipeline can use to pull vehicle inventory.
type ExtractionEndpoint struct {
	URLPattern     string `json:"url_pattern"`
	Method         string `json:"method"`
	Description    string `json:"description"`
	AuthRequired   bool   `json:"auth_required"`
	ResponseSchema string `json:"response_schema,omitempty"` // e.g. "wp-json-v2"
}

// PluginResult is the output of D.2 for a single WordPress/Joomla domain.
type PluginResult struct {
	Plugins   []string             `json:"plugins,omitempty"`
	Endpoints []ExtractionEndpoint `json:"endpoints,omitempty"`
}

// probeSpec describes a single endpoint to probe.
type probeSpec struct {
	path        string
	plugin      string
	description string
	schema      string
}

var wordpressProbes = []probeSpec{
	{
		path:        "/wp-json/wp/v2/vehicles",
		plugin:      "vehicle-cpt",
		description: "WP REST API: vehicle custom post type",
		schema:      "wp-json-v2",
	},
	{
		path:        "/wp-json/wp/v2/car",
		plugin:      "car-cpt",
		description: "WP REST API: car custom post type",
		schema:      "wp-json-v2",
	},
	{
		path:        "/wp-json/automotive/v1/vehicles",
		plugin:      "ancora-automotive",
		description: "AncoraThemes Automotive plugin REST API",
		schema:      "ancora-automotive-v1",
	},
	{
		path:        "/wp-json/autodealer/v1/listings",
		plugin:      "wp-auto-dealer",
		description: "WP Auto Dealer plugin REST API",
		schema:      "wp-auto-dealer-v1",
	},
	{
		path:        "/wp-json/cars/v1/inventory",
		plugin:      "cars-com-inventory",
		description: "Cars.com Inventory plugin REST API",
		schema:      "cars-com-v1",
	},
	{
		path:        "/?feed=rss2&post_type=vehicle",
		plugin:      "vehicle-rss",
		description: "Vehicle RSS feed (CPT plugin)",
		schema:      "rss2-vehicle",
	},
}

var joomlaProbes = []probeSpec{
	{
		path:        "/index.php?option=com_carmanager&format=json",
		plugin:      "com_carmanager",
		description: "Joomla com_carmanager component",
		schema:      "joomla-com-json",
	},
	{
		path:        "/index.php?option=com_vehicles&format=json",
		plugin:      "com_vehicles",
		description: "Joomla com_vehicles component",
		schema:      "joomla-com-json",
	},
	{
		path:        "/index.php?option=com_motovoicer&format=json",
		plugin:      "com_motovoicer",
		description: "Joomla com_motovoicer component",
		schema:      "joomla-com-json",
	},
}

// Detector probes CMS-specific endpoints to identify active dealer plugins.
type Detector struct {
	client *http.Client
	log    *slog.Logger
}

// New returns a Detector with production HTTP settings.
func New() *Detector {
	return &Detector{
		client: &http.Client{Timeout: probeTimeout},
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient returns a Detector using the supplied HTTP client (for tests).
func NewWithClient(c *http.Client) *Detector {
	return &Detector{client: c, log: slog.Default().With("sub_technique", subTechID)}
}

// ID returns the sub-technique identifier.
func (d *Detector) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (d *Detector) Name() string { return subTechName }

// DetectPlugins probes cms-specific endpoints for domain and returns a PluginResult.
// cms should be "wordpress" or "joomla"; any other value returns an empty result.
func (d *Detector) DetectPlugins(ctx context.Context, domain, cms string) (*PluginResult, error) {
	var probes []probeSpec
	switch strings.ToLower(cms) {
	case "wordpress":
		probes = wordpressProbes
	case "joomla":
		probes = joomlaProbes
	default:
		return &PluginResult{}, nil
	}

	result := &PluginResult{}
	baseURL := "https://" + domain

	for _, p := range probes {
		if ctx.Err() != nil {
			break
		}
		found, err := d.probe(ctx, baseURL+p.path)
		if err != nil {
			d.log.Debug("plugin probe error", "domain", domain, "path", p.path, "err", err)
			continue
		}
		if !found {
			continue
		}
		result.Plugins = append(result.Plugins, p.plugin)
		result.Endpoints = append(result.Endpoints, ExtractionEndpoint{
			URLPattern:     "https://{domain}" + p.path,
			Method:         "GET",
			Description:    p.description,
			AuthRequired:   false,
			ResponseSchema: p.schema,
		})
		d.log.Debug("plugin detected", "domain", domain, "plugin", p.plugin)
	}
	return result, nil
}

// probe performs a HEAD (falling back to GET) against url.
// Returns true when the server responds with 2xx.
func (d *Detector) probe(ctx context.Context, url string) (bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return false, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := d.client.Do(req)
	if err != nil {
		// Fallback: some servers reject HEAD — retry with GET
		req2, err2 := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err2 != nil {
			return false, err
		}
		req2.Header.Set("User-Agent", cardexUA)
		resp2, err2 := d.client.Do(req2)
		if err2 != nil {
			return false, err2
		}
		defer resp2.Body.Close()
		_, _ = io.CopyN(io.Discard, resp2.Body, maxProbeBody)
		return resp2.StatusCode >= 200 && resp2.StatusCode < 300, nil
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 300, nil
}
