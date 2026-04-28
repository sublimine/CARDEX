// Package nl_kvk implements sub-technique A.NL.1 — KvK Handelsregister Zoeken API
// plus KvK bulk open dataset for density statistics.
//
// Dual-path strategy (supervisor-approved 2026-04-14):
//
// Path 1 — Bulk density (Path1BulkDensity):
//   Download https://www.kvk.nl/download/kvk-open-dataset-basis-bedrijfsgegevens.zip
//   Parse semicolon-delimited CSV, filter SBI 4511/4519, store aggregate counts
//   per pc4 postal zone in `nl_dealer_density_by_pc4` (used by Familia B for
//   geo coverage analysis). This dataset is anonymised — no company names/KVK
//   numbers — so it does NOT produce KG dealer entities directly.
//
// Path 2 — Keyword API search (Path2KeywordSearch):
//   KvK Zoeken API v2 — no SBI filter available in free tier.
//   Workaround: search by automotive business name keywords (autobedrijf,
//   automobiel, garage, occasion, autohandel) using the `naam` parameter.
//   Rate limit: 100 req/day free tier, enforced via `rate_limit_state` table
//   in the KG SQLite. At service startup, remaining daily budget is read from
//   SQLite; when quota is exhausted, Run returns cleanly and logs resumption
//   time for the next calendar day.
//
// Config: KVK_API_KEY (required for Path 2), KVK_DB_PATH (same as DISCOVERY_DB_PATH)
package nl_kvk

import (
	"archive/zip"
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	zoekenBaseURL = "https://api.kvk.nl/api/v2/zoeken"
	bulkDataURL   = "https://www.kvk.nl/download/kvk-open-dataset-basis-bedrijfsgegevens.zip"
	cardexUA      = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID     = "A.NL.1"
	subTechName   = "KvK Handelsregister Zoeken API + bulk density"
	familyID      = "A"
	countryNL     = "NL"

	// kvkDailyLimit: free tier allows 100 requests/calendar day.
	kvkDailyLimit = 100

	// resultsPerPage: max results per Zoeken API call.
	resultsPerPage = 100

	// sbiTargets: SBI codes for automotive dealers.
	sbiTarget4511 = "4511"
	sbiTarget4519 = "4519"
)

// searchKeywords cycles through automotive business name keywords.
var searchKeywords = []string{
	"autobedrijf",
	"automobiel",
	"autohandel",
	"autocentrum",
	"occasions",
	"garage",
	"dealer",
	"autogroep",
	"autohuis",
}

// KvK implements runner.SubTechnique for A.NL.1.
type KvK struct {
	graph      kg.KnowledgeGraph
	db         *sql.DB
	apiKey     string
	apiBaseURL string
	bulkURL    string
	client     *http.Client
	log        *slog.Logger
}

// New creates a KvK sub-technique executor.
// db: the KG SQLite database (used for rate_limit_state table).
// apiKey: KvK API key (required for Path 2 searches).
func New(graph kg.KnowledgeGraph, db *sql.DB, apiKey string) *KvK {
	return NewWithBaseURL(graph, db, apiKey, zoekenBaseURL, bulkDataURL)
}

// NewWithBaseURL creates a KvK executor with custom base URLs (for tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, db *sql.DB, apiKey, apiBase, bulk string) *KvK {
	return &KvK{
		graph:      graph,
		db:         db,
		apiKey:     apiKey,
		apiBaseURL: apiBase,
		bulkURL:    bulk,
		client:     &http.Client{Timeout: 60 * time.Second},
		log:        slog.Default().With("sub_technique", subTechID),
	}
}

func (k *KvK) ID() string      { return subTechID }
func (k *KvK) Name() string    { return subTechName }
func (k *KvK) Country() string { return countryNL }

// Run executes both paths: bulk density ingest and keyword API search.
func (k *KvK) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryNL,
	}

	// Ensure rate_limit_state table exists.
	if err := k.ensureRateLimitTable(ctx); err != nil {
		return result, fmt.Errorf("kvk.Run: ensure rate limit table: %w", err)
	}

	// Path 1: bulk density (separate operation, errors are non-fatal).
	if err := k.runBulkDensity(ctx); err != nil {
		k.log.Warn("kvk: bulk density ingest failed (non-fatal)", "err", err)
	}

	// Path 2: keyword API search (if API key provided).
	if k.apiKey == "" {
		k.log.Info("kvk: KVK_API_KEY not set — skipping keyword API search")
		result.Duration = time.Since(start)
		return result, nil
	}

	if err := k.runKeywordSearch(ctx, result); err != nil {
		return result, err
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryNL).Observe(result.Duration.Seconds())
	return result, nil
}

// ── Path 1: Bulk density ───────────────────────────────────────────────────

// runBulkDensity downloads the KvK anonymised bulk dataset, filters SBI 4511/4519,
// and stores aggregate counts per pc2 postal zone for Familia B.
func (k *KvK) runBulkDensity(ctx context.Context) error {
	if err := k.ensureDensityTable(ctx); err != nil {
		return err
	}

	k.log.Info("kvk: downloading bulk density dataset", "url", k.bulkURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, k.bulkURL, nil)
	if err != nil {
		return fmt.Errorf("kvk: build bulk request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := k.client.Do(req)
	if err != nil {
		return fmt.Errorf("kvk: bulk download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("kvk: bulk HTTP %d", resp.StatusCode)
	}

	// Read zip into memory (file is ~50 MB).
	body, err := io.ReadAll(io.LimitReader(resp.Body, 200<<20)) // 200 MB cap
	if err != nil {
		return fmt.Errorf("kvk: read bulk body: %w", err)
	}

	zr, err := zip.NewReader(bytes.NewReader(body), int64(len(body)))
	if err != nil {
		return fmt.Errorf("kvk: open zip: %w", err)
	}

	for _, f := range zr.File {
		if !strings.HasSuffix(strings.ToLower(f.Name), ".csv") {
			continue
		}
		if err := k.parseBulkCSV(ctx, f); err != nil {
			k.log.Warn("kvk: bulk CSV parse error", "file", f.Name, "err", err)
		}
	}
	return nil
}

// parseBulkCSV parses one CSV from the bulk dataset and aggregates SBI 4511/4519
// counts into nl_dealer_density_by_pc4.
func (k *KvK) parseBulkCSV(ctx context.Context, f *zip.File) error {
	rc, err := f.Open()
	if err != nil {
		return err
	}
	defer rc.Close()

	r := csv.NewReader(rc)
	r.Comma = ';'
	r.LazyQuotes = true

	// Read header.
	header, err := r.Read()
	if err != nil {
		return err
	}

	// Find column indices.
	sbiCol, pc4Col := -1, -1
	for i, col := range header {
		switch strings.ToLower(strings.TrimSpace(col)) {
		case "sbi_activiteiten", "sbiactiviteiten", "sbi":
			sbiCol = i
		case "postcode", "pc4", "pc4_code":
			pc4Col = i
		}
	}
	if sbiCol == -1 {
		return nil // not the SBI-bearing CSV file — skip
	}

	counts := make(map[string]int) // pc4 → count
	for {
		if ctx.Err() != nil {
			break
		}
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}
		if sbiCol >= len(rec) {
			continue
		}
		sbi := strings.TrimSpace(rec[sbiCol])
		if sbi != sbiTarget4511 && sbi != sbiTarget4519 &&
			!strings.HasPrefix(sbi, sbiTarget4511) &&
			!strings.HasPrefix(sbi, sbiTarget4519) {
			continue
		}
		pc4 := ""
		if pc4Col >= 0 && pc4Col < len(rec) {
			pc4 = strings.TrimSpace(rec[pc4Col])
			if len(pc4) > 2 {
				pc4 = pc4[:2] // aggregate to pc2
			}
		}
		counts[pc4]++
	}

	// Upsert density counts.
	const upsertDensity = `
INSERT INTO nl_dealer_density_by_pc4(pc4_prefix, sbi, count, updated_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(pc4_prefix, sbi) DO UPDATE SET count = excluded.count, updated_at = excluded.updated_at`
	now := time.Now().UTC().Format(time.RFC3339)
	for pc4, count := range counts {
		if _, err := k.db.ExecContext(ctx, upsertDensity, pc4, "4511", count, now); err != nil {
			k.log.Warn("kvk: density upsert", "pc4", pc4, "err", err)
		}
	}
	k.log.Info("kvk: bulk density updated", "pc4_zones", len(counts))
	return nil
}

// ── Path 2: Keyword API search ─────────────────────────────────────────────

// runKeywordSearch iterates through automotive keywords and pages the Zoeken API.
func (k *KvK) runKeywordSearch(ctx context.Context, result *runner.SubTechniqueResult) error {
	remaining, err := k.remainingQuota(ctx)
	if err != nil {
		return fmt.Errorf("kvk: read quota: %w", err)
	}
	if remaining <= 0 {
		k.log.Info("kvk: daily API quota exhausted — will resume tomorrow")
		return nil
	}

	for _, keyword := range searchKeywords {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if remaining <= 0 {
			k.log.Info("kvk: quota exhausted mid-run", "keyword", keyword)
			break
		}

		added, used, err := k.searchByKeyword(ctx, keyword, remaining)
		result.Discovered += added
		remaining -= used

		if err != nil {
			result.Errors++
			k.log.Warn("kvk: keyword search error", "keyword", keyword, "err", err)
		}

		if err := k.recordUsage(ctx, used); err != nil {
			k.log.Warn("kvk: record usage error", "err", err)
		}
	}
	return nil
}

// searchByKeyword pages through Zoeken API results for a single keyword.
// Returns: (discovered count, requests used, error).
func (k *KvK) searchByKeyword(ctx context.Context, keyword string, quota int) (int, int, error) {
	discovered, used := 0, 0

	for pagina := 1; ; pagina++ {
		if used >= quota {
			break
		}

		params := url.Values{
			"naam":                 {keyword},
			"pagina":               {fmt.Sprintf("%d", pagina)},
			"resultatenPerPagina":  {fmt.Sprintf("%d", resultsPerPage)},
			"inclusiefInactieveRegistraties": {"false"},
		}
		reqURL := k.apiBaseURL + "?" + params.Encode()

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
		if err != nil {
			return discovered, used, fmt.Errorf("kvk: build request: %w", err)
		}
		req.Header.Set("User-Agent", cardexUA)
		req.Header.Set("apikey", k.apiKey)
		req.Header.Set("Accept", "application/json")

		resp, err := k.client.Do(req)
		used++
		if err != nil {
			metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
			return discovered, used, fmt.Errorf("kvk: http get: %w", err)
		}

		body, _ := io.ReadAll(io.LimitReader(resp.Body, 5<<20))
		resp.Body.Close()

		metrics.SubTechniqueRequests.WithLabelValues(subTechID,
			fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

		if resp.StatusCode == http.StatusTooManyRequests {
			k.log.Warn("kvk: 429 rate limited")
			break
		}
		if resp.StatusCode != http.StatusOK {
			return discovered, used, fmt.Errorf("kvk: HTTP %d: %s",
				resp.StatusCode, truncate(string(body), 200))
		}

		var page kvkPage
		if err := json.Unmarshal(body, &page); err != nil {
			return discovered, used, fmt.Errorf("kvk: decode JSON: %w", err)
		}

		for i := range page.Resultaten {
			if err := k.upsertCompany(ctx, &page.Resultaten[i]); err != nil {
				k.log.Warn("kvk: upsert error",
					"kvk_num", page.Resultaten[i].KvKNummer, "err", err)
				continue
			}
			discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryNL).Inc()
		}

		if len(page.Resultaten) < resultsPerPage || page.Volgende == "" {
			break // last page
		}
	}
	return discovered, used, nil
}

// ── KvK API JSON types ─────────────────────────────────────────────────────

type kvkPage struct {
	Resultaten []kvkCompany `json:"resultaten"`
	Volgende   string       `json:"volgende"`
	Totaal     int          `json:"totaal"`
}

type kvkCompany struct {
	KvKNummer string   `json:"kvkNummer"`
	Naam      string   `json:"naam"`
	Type      string   `json:"type"`
	Actief    bool     `json:"actief"`
	Adres     *kvkAddr `json:"adres"`
}

type kvkAddr struct {
	BinnenlandsAdres *kvkBinnenlands `json:"binnenlandsAdres"`
}

type kvkBinnenlands struct {
	Straatnaam  string `json:"straatnaam"`
	Huisnummer  int    `json:"huisnummer"`
	Postcode    string `json:"postcode"`
	Plaats      string `json:"plaats"`
}

// upsertCompany writes one KvK company into the KG.
func (k *KvK) upsertCompany(ctx context.Context, c *kvkCompany) error {
	if c.KvKNummer == "" || c.Naam == "" {
		return nil
	}
	now := time.Now().UTC()

	existing, err := k.graph.FindDealerByIdentifier(ctx, kg.IdentifierKvK, c.KvKNummer)
	if err != nil {
		return err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	status := kg.StatusActive
	if !c.Actief {
		status = kg.StatusDormant
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     c.Naam,
		NormalizedName:    strings.ToLower(c.Naam),
		CountryCode:       countryNL,
		Status:            status,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := k.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	if err := k.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierKvK,
		IdentifierValue: c.KvKNummer,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	// Location from API address.
	if c.Adres != nil && c.Adres.BinnenlandsAdres != nil {
		addr := c.Adres.BinnenlandsAdres
		loc := &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			CountryCode:    countryNL,
			SourceFamilies: familyID,
		}
		if addr.Postcode != "" {
			loc.PostalCode = &addr.Postcode
		}
		if addr.Plaats != "" {
			loc.City = &addr.Plaats
		}
		if addr.Straatnaam != "" {
			line := fmt.Sprintf("%s %d", addr.Straatnaam, addr.Huisnummer)
			if addr.Huisnummer == 0 {
				line = addr.Straatnaam
			}
			loc.AddressLine1 = &line
		}
		if err := k.graph.AddLocation(ctx, loc); err != nil {
			return err
		}
	}

	kvkRef := c.KvKNummer
	return k.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &kvkRef,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// ── Rate limit state ───────────────────────────────────────────────────────

const rateLimitTable = `
CREATE TABLE IF NOT EXISTS rate_limit_state (
  api_name    TEXT PRIMARY KEY,
  reqs_today  INTEGER NOT NULL DEFAULT 0,
  window_start TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nl_dealer_density_by_pc4 (
  pc4_prefix  TEXT NOT NULL,
  sbi         TEXT NOT NULL,
  count       INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT NOT NULL,
  PRIMARY KEY (pc4_prefix, sbi)
);`

func (k *KvK) ensureRateLimitTable(ctx context.Context) error {
	_, err := k.db.ExecContext(ctx, rateLimitTable)
	return err
}

func (k *KvK) ensureDensityTable(ctx context.Context) error {
	_, err := k.db.ExecContext(ctx,
		`CREATE TABLE IF NOT EXISTS nl_dealer_density_by_pc4 (
            pc4_prefix TEXT NOT NULL,
            sbi        TEXT NOT NULL,
            count      INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (pc4_prefix, sbi)
        )`)
	return err
}

// remainingQuota returns how many requests remain for today's KvK API budget.
func (k *KvK) remainingQuota(ctx context.Context) (int, error) {
	todayKey := time.Now().UTC().Format("2006-01-02")

	var reqs int
	var window string
	err := k.db.QueryRowContext(ctx,
		`SELECT reqs_today, window_start FROM rate_limit_state WHERE api_name='kvk'`,
	).Scan(&reqs, &window)

	if err == sql.ErrNoRows {
		// First use — insert fresh state.
		_, err = k.db.ExecContext(ctx,
			`INSERT INTO rate_limit_state(api_name, reqs_today, window_start) VALUES('kvk', 0, ?)`,
			todayKey)
		return kvkDailyLimit, err
	}
	if err != nil {
		return 0, fmt.Errorf("kvk: query rate limit: %w", err)
	}

	// Reset if the window is a past day.
	if window != todayKey {
		_, err = k.db.ExecContext(ctx,
			`UPDATE rate_limit_state SET reqs_today=0, window_start=? WHERE api_name='kvk'`,
			todayKey)
		return kvkDailyLimit, err
	}

	return kvkDailyLimit - reqs, nil
}

// recordUsage increments the request counter for today.
func (k *KvK) recordUsage(ctx context.Context, used int) error {
	todayKey := time.Now().UTC().Format("2006-01-02")
	_, err := k.db.ExecContext(ctx,
		`UPDATE rate_limit_state SET reqs_today = reqs_today + ?, window_start = ?
         WHERE api_name = 'kvk'`,
		used, todayKey)
	return err
}

// ── String helpers ─────────────────────────────────────────────────────────

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}

// ── File-based bulk path ───────────────────────────────────────────────────

// OpenBulkFile opens a pre-downloaded KvK bulk zip from disk (for testing or
// offline operation). Callers can pass a custom file path via constructor.
func OpenBulkFile(path string) (*os.File, int64, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, 0, fmt.Errorf("kvk: open bulk file %q: %w", path, err)
	}
	fi, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, 0, err
	}
	return f, fi.Size(), nil
}

// ParseBulkFromReader exposes the CSV parsing logic for testing.
func (k *KvK) ParseBulkFromReader(ctx context.Context, name string, rc io.Reader) (map[string]int, error) {
	r := csv.NewReader(rc)
	r.Comma = ';'
	r.LazyQuotes = true

	header, err := r.Read()
	if err != nil {
		return nil, err
	}

	sbiCol, pc4Col := -1, -1
	for i, col := range header {
		switch strings.ToLower(strings.TrimSpace(col)) {
		case "sbi_activiteiten", "sbiactiviteiten", "sbi":
			sbiCol = i
		case "postcode", "pc4", "pc4_code":
			pc4Col = i
		}
	}
	if sbiCol == -1 {
		return nil, nil // not the right file
	}

	counts := make(map[string]int)
	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}
		if sbiCol >= len(rec) {
			continue
		}
		sbi := strings.TrimSpace(rec[sbiCol])
		if !strings.HasPrefix(sbi, sbiTarget4511) && !strings.HasPrefix(sbi, sbiTarget4519) {
			continue
		}
		pc4 := ""
		if pc4Col >= 0 && pc4Col < len(rec) {
			pc4 = strings.TrimSpace(rec[pc4Col])
			if len(pc4) > 2 {
				pc4 = pc4[:2]
			}
		}
		counts[pc4]++
	}
	return counts, nil
}

// ensure unused import compile
var _ = filepath.Join
