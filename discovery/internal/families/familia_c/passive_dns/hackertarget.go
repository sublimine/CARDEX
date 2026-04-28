// Package passive_dns implements sub-technique C.4 — Passive DNS via Hackertarget.
//
// For each domain in the KG's dealer_web_presence table the sub-technique
// queries the Hackertarget Host Search API and stores any newly-discovered
// subdomains as additional DealerWebPresence rows.
//
// Hackertarget Host Search API (verified 2026-04-14):
//
//	GET https://api.hackertarget.com/hostsearch/?q={domain}
//
// Response: plain-text CSV, one record per line:
//
//	subdomain.example.de,1.2.3.4
//
// Free tier: 50 requests/day per IP (enforced client-side via rate_limit_state
// SQLite table shared with the KvK sub-technique).
//
// Rate limiting: 1 request per 2 seconds between domains; stops immediately
// when the daily quota is exhausted.
package passive_dns

import (
	"bufio"
	"context"
	"database/sql"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultHackerTargetURL = "https://api.hackertarget.com/hostsearch"
	defaultReqInterval     = 2 * time.Second
	cardexUA               = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	apiName                = "hackertarget_dns"
	dailyLimit             = 50
	familyID               = "C"
	subTechID              = "C.4"
	subTechName            = "Passive DNS / Hackertarget"
)

// SubdomainRecord holds a subdomain and its resolved IP address.
type SubdomainRecord struct {
	Subdomain string
	IP        string
}

// HackerTarget executes C.4 sub-technique passive-DNS queries.
type HackerTarget struct {
	graph       kg.KnowledgeGraph
	db          *sql.DB
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New creates a HackerTarget executor with the production endpoint.
func New(graph kg.KnowledgeGraph, database *sql.DB) *HackerTarget {
	return NewWithBaseURL(graph, database, defaultHackerTargetURL, defaultReqInterval)
}

// NewWithBaseURL creates a HackerTarget executor with a custom endpoint and
// request interval (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, database *sql.DB, baseURL string, reqInterval time.Duration) *HackerTarget {
	return &HackerTarget{
		graph:       graph,
		db:          database,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (h *HackerTarget) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (h *HackerTarget) Name() string { return subTechName }

// RunForDomain queries the Hackertarget API for passive-DNS records associated
// with the given domain and returns all subdomain records found.
func (h *HackerTarget) RunForDomain(ctx context.Context, domain string) ([]SubdomainRecord, error) {
	reqURL := h.baseURL + "/?q=" + url.QueryEscape(domain)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("hackertarget: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := h.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("hackertarget: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
		return nil, fmt.Errorf("hackertarget: HTTP %d: %s", resp.StatusCode, string(raw))
	}

	return parseCSVResponse(resp.Body, domain)
}

// RunAll iterates over all dealer_web_presence entries for the given country,
// queries Hackertarget for each domain (respecting the daily quota), and
// upserts newly-discovered subdomains into the KG.
func (h *HackerTarget) RunAll(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if err := h.ensureRateLimitTable(ctx); err != nil {
		return result, fmt.Errorf("hackertarget.RunAll: init rate limit table: %w", err)
	}

	presences, err := h.graph.ListWebPresencesByCountry(ctx, country)
	if err != nil {
		return result, fmt.Errorf("hackertarget.RunAll %s: list presences: %w", country, err)
	}

	for i, wp := range presences {
		if ctx.Err() != nil {
			break
		}

		remaining, err := h.remainingQuota(ctx)
		if err != nil {
			h.log.Warn("hackertarget: quota check failed", "err", err)
			result.Errors++
			break
		}
		if remaining <= 0 {
			h.log.Info("hackertarget: daily quota exhausted", "country", country)
			break
		}

		if i > 0 && h.reqInterval > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(h.reqInterval):
			}
		}

		records, err := h.RunForDomain(ctx, wp.Domain)
		if err != nil {
			h.log.Warn("hackertarget: domain error", "domain", wp.Domain, "err", err)
			result.Errors++
			continue
		}

		if err := h.recordUsage(ctx, 1); err != nil {
			h.log.Warn("hackertarget: record usage failed", "err", err)
		}

		for _, rec := range records {
			if rec.Subdomain == wp.Domain {
				continue // skip the root domain itself
			}
			upserted, err := h.upsertSubdomain(ctx, wp.DealerID, rec)
			if err != nil {
				h.log.Warn("hackertarget: subdomain upsert error", "subdomain", rec.Subdomain, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Confirmed++
				metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
			}
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	h.log.Info("hackertarget: done",
		"country", country,
		"processed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsertSubdomain inserts a new DealerWebPresence row for a subdomain
// discovered via passive DNS. Returns true when a new row was created.
func (h *HackerTarget) upsertSubdomain(ctx context.Context, dealerID string, rec SubdomainRecord) (bool, error) {
	existing, err := h.graph.FindDealerIDByDomain(ctx, rec.Subdomain)
	if err != nil {
		return false, err
	}
	if existing != "" {
		return false, nil // already known
	}

	wp := &kg.DealerWebPresence{
		WebID:                ulid.Make().String(),
		DealerID:             dealerID,
		Domain:               rec.Subdomain,
		URLRoot:              "https://" + rec.Subdomain,
		DiscoveredByFamilies: familyID,
	}
	if err := h.graph.UpsertWebPresence(ctx, wp); err != nil {
		return false, err
	}
	return true, nil
}

// HealthCheck sends a minimal probe to verify the Hackertarget API is reachable.
func (h *HackerTarget) HealthCheck(ctx context.Context) error {
	reqURL := h.baseURL + "/?q=example.com"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := h.client.Do(req)
	if err != nil {
		return fmt.Errorf("hackertarget health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("hackertarget health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Rate limit state ──────────────────────────────────────────────────────────

const rateLimitTableSQL = `
CREATE TABLE IF NOT EXISTS rate_limit_state (
  api_name     TEXT PRIMARY KEY,
  reqs_today   INTEGER NOT NULL DEFAULT 0,
  window_start TEXT NOT NULL
);`

func (h *HackerTarget) ensureRateLimitTable(ctx context.Context) error {
	_, err := h.db.ExecContext(ctx, rateLimitTableSQL)
	return err
}

func (h *HackerTarget) remainingQuota(ctx context.Context) (int, error) {
	todayKey := time.Now().UTC().Format("2006-01-02")

	var reqs int
	var window string
	err := h.db.QueryRowContext(ctx,
		`SELECT reqs_today, window_start FROM rate_limit_state WHERE api_name = ?`,
		apiName,
	).Scan(&reqs, &window)

	if err == sql.ErrNoRows {
		_, err = h.db.ExecContext(ctx,
			`INSERT INTO rate_limit_state(api_name, reqs_today, window_start) VALUES(?, 0, ?)`,
			apiName, todayKey)
		return dailyLimit, err
	}
	if err != nil {
		return 0, fmt.Errorf("hackertarget: query rate limit: %w", err)
	}

	if window != todayKey {
		_, err = h.db.ExecContext(ctx,
			`UPDATE rate_limit_state SET reqs_today=0, window_start=? WHERE api_name=?`,
			todayKey, apiName)
		return dailyLimit, err
	}

	return dailyLimit - reqs, nil
}

func (h *HackerTarget) recordUsage(ctx context.Context, used int) error {
	todayKey := time.Now().UTC().Format("2006-01-02")
	_, err := h.db.ExecContext(ctx,
		`UPDATE rate_limit_state SET reqs_today = reqs_today + ?, window_start = ?
		 WHERE api_name = ?`,
		used, todayKey, apiName)
	return err
}

// ── CSV parser ────────────────────────────────────────────────────────────────

// parseCSVResponse reads the Hackertarget CSV response body and returns
// SubdomainRecord entries for lines that are valid "subdomain,ip" pairs.
// Lines that begin with "error" (API error messages) are silently skipped.
func parseCSVResponse(body io.Reader, rootDomain string) ([]SubdomainRecord, error) {
	var records []SubdomainRecord
	scanner := bufio.NewScanner(io.LimitReader(body, 1<<20)) // 1 MiB safety cap
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(strings.ToLower(line), "error") {
			continue
		}
		parts := strings.SplitN(line, ",", 2)
		if len(parts) != 2 {
			continue
		}
		subdomain := strings.TrimSpace(parts[0])
		ip := strings.TrimSpace(parts[1])
		if subdomain == "" {
			continue
		}
		// Only accept subdomains that end with the root domain.
		if subdomain != rootDomain && !strings.HasSuffix(subdomain, "."+rootDomain) {
			continue
		}
		records = append(records, SubdomainRecord{Subdomain: subdomain, IP: ip})
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("hackertarget: read response: %w", err)
	}
	return records, nil
}
