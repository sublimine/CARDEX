// Package wayback implements sub-technique C.2 — Wayback Machine / Internet Archive.
//
// For each domain in the KG's dealer_web_presence table the sub-technique
// probes three historical timestamps (1-year, 3-year and 6-year ago) using the
// Wayback Machine availability API and records the coverage in the presence
// metadata_json field.
//
// Wayback API endpoint verified 2026-04-14:
//
//	GET https://archive.org/wayback/available?url={domain}&timestamp={YYYYMMDD}
//
// When a snapshot is available the response contains:
//
//	{"url":"...","archived_snapshots":{"closest":{"available":true,"timestamp":"20230115120000",...}},"timestamp":"..."}
//
// When no snapshot is available:
//
//	{"url":"...","archived_snapshots":{},"timestamp":"..."}
//
// Rate limiting: 1 request per second to archive.org (conservative; no
// published rate limit, but archive.org asks for respectful access).
package wayback

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"sort"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultWaybackURL  = "https://archive.org/wayback/available"
	defaultReqInterval = 1 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "C"
	subTechID          = "C.2"
	subTechName        = "Wayback Machine / Internet Archive"
)

// WaybackResult summarises the archive coverage found for a single domain.
type WaybackResult struct {
	Domain          string
	Available       bool   // true if at least one snapshot was found
	FirstSnapshot   string // YYYY-MM-DD of oldest snapshot found among the probes
	LastSnapshot    string // YYYY-MM-DD of most recent snapshot found
	SnapshotCount   int    // number of probe timestamps that returned a snapshot (0-3)
	ProbableClosure bool   // true if oldest probe (6yr ago) has snapshot but newest (1yr ago) does not
}

// Wayback executes C.2 sub-technique queries.
type Wayback struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration // delay between successive HTTP requests
	log         *slog.Logger
}

// New creates a Wayback executor with the production Wayback Machine endpoint
// and the default 1-second request interval.
func New(graph kg.KnowledgeGraph) *Wayback {
	return NewWithBaseURL(graph, defaultWaybackURL, defaultReqInterval)
}

// NewWithBaseURL creates a Wayback executor with custom endpoint and request
// interval (use interval=0 in tests to avoid blocking).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *Wayback {
	return &Wayback{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (w *Wayback) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (w *Wayback) Name() string { return subTechName }

// RunForDomain probes the Wayback Machine for a single domain at three
// historical timestamps (1-year, 3-year and 6-year ago from today).
// Returns a WaybackResult with coverage details.
func (w *Wayback) RunForDomain(ctx context.Context, domain string) (*WaybackResult, error) {
	now := time.Now().UTC()
	probeTS := []string{
		now.AddDate(-1, 0, 0).Format("20060102"), // index 0 = newest (1yr ago)
		now.AddDate(-3, 0, 0).Format("20060102"), // index 1 = middle (3yr ago)
		now.AddDate(-6, 0, 0).Format("20060102"), // index 2 = oldest (6yr ago)
	}

	found := [3]bool{}    // whether each probe returned a snapshot
	dates := [3]string{}  // snapshot dates returned (YYYYMMDD format, empty if none)

	for i, ts := range probeTS {
		snap, ok, err := w.checkSnapshot(ctx, domain, ts)
		if err != nil {
			return nil, fmt.Errorf("wayback.RunForDomain %q ts=%s: %w", domain, ts, err)
		}
		if ok && snap.Timestamp != "" {
			found[i] = true
			dates[i] = snap.Timestamp[:8] // take YYYYMMDD prefix from YYYYMMDDHHMMSS
		}

		// Respect rate limit between requests (not after the last one).
		if i < len(probeTS)-1 && w.reqInterval > 0 {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(w.reqInterval):
			}
		}
	}

	// Collect non-empty dates and sort chronologically to determine first/last.
	var nonEmpty []string
	for _, d := range dates {
		if d != "" {
			nonEmpty = append(nonEmpty, d)
		}
	}
	sort.Strings(nonEmpty)

	result := &WaybackResult{Domain: domain}
	if len(nonEmpty) > 0 {
		result.Available = true
		result.SnapshotCount = len(nonEmpty)
		result.FirstSnapshot = yyyymmddToISO(nonEmpty[0])
		result.LastSnapshot = yyyymmddToISO(nonEmpty[len(nonEmpty)-1])
	}

	// ProbableClosure: oldest probe (6yr ago, index 2) found a snapshot
	// but newest probe (1yr ago, index 0) did not — suggests site went offline.
	result.ProbableClosure = found[2] && !found[0]

	return result, nil
}

// RunAll iterates over all web presence entries for the given country,
// probes each domain, and updates dealer_web_presence.metadata_json.
func (w *Wayback) RunAll(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        country,
	}

	presences, err := w.graph.ListWebPresencesByCountry(ctx, country)
	if err != nil {
		return result, fmt.Errorf("wayback.RunAll %s: list presences: %w", country, err)
	}

	for i, wp := range presences {
		if ctx.Err() != nil {
			break
		}

		// Delay between domains (not before the first one).
		if i > 0 && w.reqInterval > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(w.reqInterval):
			}
		}

		wr, err := w.RunForDomain(ctx, wp.Domain)
		if err != nil {
			w.log.Warn("wayback: domain error", "domain", wp.Domain, "err", err)
			result.Errors++
			continue
		}

		meta := buildMetadataJSON(wr)
		if err := w.graph.UpdateWebPresenceMetadata(ctx, wp.Domain, meta); err != nil {
			w.log.Warn("wayback: metadata update error", "domain", wp.Domain, "err", err)
			result.Errors++
			continue
		}

		result.Confirmed++
		metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	w.log.Info("wayback: done",
		"country", country,
		"processed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// ── Wayback availability API ──────────────────────────────────────────────────

type waybackResponse struct {
	URL               string                     `json:"url"`
	Timestamp         string                     `json:"timestamp"`
	ArchivedSnapshots map[string]waybackSnapshot `json:"archived_snapshots"`
}

type waybackSnapshot struct {
	Available bool   `json:"available"`
	URL       string `json:"url"`
	Timestamp string `json:"timestamp"`
	Status    string `json:"status"`
}

// checkSnapshot queries the Wayback availability API for a single domain+timestamp.
// Returns the snapshot and ok=true if a snapshot is available, or (zero, false, nil)
// when no snapshot exists for that timestamp.
func (w *Wayback) checkSnapshot(ctx context.Context, domain, timestamp string) (waybackSnapshot, bool, error) {
	reqURL := w.baseURL + "?url=" + url.QueryEscape(domain) + "&timestamp=" + timestamp

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return waybackSnapshot{}, false, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := w.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return waybackSnapshot{}, false, fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
		return waybackSnapshot{}, false, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(raw))
	}

	var parsed waybackResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return waybackSnapshot{}, false, fmt.Errorf("decode JSON: %w", err)
	}

	snap, ok := parsed.ArchivedSnapshots["closest"]
	if !ok || !snap.Available {
		return waybackSnapshot{}, false, nil
	}
	return snap, true, nil
}

// HealthCheck sends a minimal probe to verify the Wayback API is reachable.
func (w *Wayback) HealthCheck(ctx context.Context) error {
	reqURL := w.baseURL + "?url=example.com"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("wayback health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("wayback health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// yyyymmddToISO converts a YYYYMMDD string to YYYY-MM-DD ISO date format.
func yyyymmddToISO(s string) string {
	if len(s) < 8 {
		return s
	}
	return s[:4] + "-" + s[4:6] + "-" + s[6:8]
}

// buildMetadataJSON produces a JSON object capturing wayback coverage for
// storage in dealer_web_presence.metadata_json.
func buildMetadataJSON(r *WaybackResult) string {
	type coverage struct {
		Available       bool   `json:"available"`
		FirstSnapshot   string `json:"first_snapshot,omitempty"`
		LastSnapshot    string `json:"last_snapshot,omitempty"`
		SnapshotCount   int    `json:"snapshot_count,omitempty"`
		ProbableClosure bool   `json:"probable_closure,omitempty"`
	}
	type meta struct {
		WaybackCoverage coverage  `json:"wayback_coverage"`
		UpdatedAt       string    `json:"updated_at"`
		UpdatedBy       string    `json:"updated_by"`
	}
	m := meta{
		WaybackCoverage: coverage{
			Available:       r.Available,
			FirstSnapshot:   r.FirstSnapshot,
			LastSnapshot:    r.LastSnapshot,
			SnapshotCount:   r.SnapshotCount,
			ProbableClosure: r.ProbableClosure,
		},
		UpdatedAt: time.Now().UTC().Format(time.RFC3339),
		UpdatedBy: subTechID,
	}
	b, _ := json.Marshal(m)
	return string(b)
}

