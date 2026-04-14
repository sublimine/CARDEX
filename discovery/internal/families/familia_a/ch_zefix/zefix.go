// Package ch_zefix implements sub-technique A.CH.1 — opendata.swiss CKAN + Zefix HTML fallback.
//
// Coverage: Swiss commercial register entities with NOGA 45.11
// (Detailhandel mit Motorfahrzeugen/Zweirädern) — car and motorcycle dealers.
//
// Two-path strategy (supervisor-approved 2026-04-14):
//
// Primary path — opendata.swiss CKAN:
//
//	GET https://opendata.swiss/api/3/action/package_search?q=firmen+zweck+rechtsform+standort&rows=10
//	Inspect returned packages for a downloadable CSV resource.
//	Parse the CSV and look for a NOGA column (noga_code, noga, aktivitaet_noga, …).
//	If found: filter for prefix "4511" → upsert as DealerEntity with ZEFIX_UID identifier.
//	If no NOGA column exists in any resource → trigger fallback path.
//
// Fallback path — Zefix public HTML keyword search (goquery):
//
//	For each automotive keyword, GET
//	https://www.zefix.ch/en/search/entity/list?name={keyword}&searchType=0&status=ACTIVE
//	Parse HTML response with goquery — probes both table and card layouts so the
//	parser survives minor HTML structure changes on the Zefix website.
//	Rate: 1 req / 3 s.
//
// Identifier type: ZEFIX_UID (canonical format CHE-NNN.NNN.NNN).
//
// Legal:
//
//	opendata.swiss — CC BY 4.0 Switzerland; open data, reuse permitted.
//	zefix.ch — public company directory service; ToS permits lookup use.
package ch_zefix

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"
	"golang.org/x/time/rate"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultCKANSearchURL  = "https://opendata.swiss/api/3/action/package_search"
	defaultZefixSearchURL = "https://www.zefix.ch/en/search/entity/list"
	cardexUA              = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID             = "A.CH.1"
	subTechName           = "opendata.swiss CKAN + Zefix HTML"
	familyID              = "A"
	countryCH             = "CH"
	nogaTarget            = "4511"
)

// automotiveKeywords are used when the CKAN primary path yields no NOGA data.
// Each keyword triggers one search request on zefix.ch.
var automotiveKeywords = []string{
	"Autohandel",
	"Occasionen",
	"Fahrzeughandel",
	"Automobilhandel",
	"Autohaus",
	"Autohändler",
	"Automobile",
}

// Zefix implements runner.SubTechnique for A.CH.1.
type Zefix struct {
	graph          kg.KnowledgeGraph
	client         *http.Client
	limiter        *rate.Limiter
	log            *slog.Logger
	ckanURL        string // overridable for tests
	zefixSearchURL string // overridable for tests
}

// New creates a Zefix sub-technique executor.
func New(graph kg.KnowledgeGraph) *Zefix {
	return NewWithURLs(graph, defaultCKANSearchURL, defaultZefixSearchURL)
}

// NewWithURLs creates a Zefix executor with custom base URLs (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, ckanURL, zefixURL string) *Zefix {
	return &Zefix{
		graph:          graph,
		client:         &http.Client{Timeout: 60 * time.Second},
		limiter:        rate.NewLimiter(rate.Every(3*time.Second), 1),
		log:            slog.Default().With("sub_technique", subTechID),
		ckanURL:        ckanURL,
		zefixSearchURL: zefixURL,
	}
}

func (z *Zefix) ID() string      { return subTechID }
func (z *Zefix) Name() string    { return subTechName }
func (z *Zefix) Country() string { return countryCH }

// Run executes A.CH.1: CKAN primary path, HTML keyword fallback if no NOGA data found.
func (z *Zefix) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryCH,
	}

	found, err := z.runCKAN(ctx, result)
	if err != nil {
		z.log.Warn("zefix: CKAN primary path error", "err", err)
		result.Errors++
	}

	if !found {
		z.log.Info("zefix: CKAN path yielded no NOGA-coded data — running HTML keyword fallback")
		if ferr := z.runZefixHTML(ctx, result); ferr != nil {
			result.Errors++
			z.log.Warn("zefix: HTML fallback error", "err", ferr)
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryCH).Observe(result.Duration.Seconds())
	z.log.Info("zefix run complete",
		"discovered", result.Discovered,
		"errors", result.Errors,
		"duration", result.Duration,
	)
	return result, nil
}

// ── CKAN primary path ────────────────────────────────────────────────────────

// ckanSearchResponse is the top-level CKAN action API response envelope.
type ckanSearchResponse struct {
	Success bool `json:"success"`
	Result  struct {
		Count   int          `json:"count"`
		Results []ckanPackage `json:"results"`
	} `json:"result"`
}

// ckanPackage is a single CKAN dataset (package).
type ckanPackage struct {
	ID        string         `json:"id"`
	Title     string         `json:"title"`
	Resources []ckanResource `json:"resources"`
}

// ckanResource is a downloadable resource within a CKAN dataset.
type ckanResource struct {
	URL    string `json:"url"`
	Format string `json:"format"`
	Name   string `json:"name"`
}

// ckanEntry holds normalized data from a CKAN CSV row that matched NOGA 4511.
type ckanEntry struct {
	UID       string
	Name      string
	NOGA      string
	Canton    string
	City      string
	LegalForm string
}

// runCKAN searches opendata.swiss for a dataset containing company data with NOGA codes.
// Returns (true, nil) if NOGA-coded entries were found and upserted.
// Returns (false, nil) if datasets exist but none carry a NOGA column → triggers HTML fallback.
// Returns (false, err) on hard network or parse failure.
func (z *Zefix) runCKAN(ctx context.Context, result *runner.SubTechniqueResult) (bool, error) {
	searchURL := z.ckanURL + "?q=firmen+zweck+rechtsform+standort&rows=10"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return false, fmt.Errorf("zefix ckan: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := z.client.Do(req)
	if err != nil {
		return false, fmt.Errorf("zefix ckan: http get: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("zefix ckan: HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 5<<20)) // 5 MB
	if err != nil {
		return false, fmt.Errorf("zefix ckan: read body: %w", err)
	}

	var searchResp ckanSearchResponse
	if err := json.Unmarshal(body, &searchResp); err != nil {
		return false, fmt.Errorf("zefix ckan: parse JSON: %w", err)
	}

	if !searchResp.Success || searchResp.Result.Count == 0 {
		z.log.Debug("zefix ckan: no packages found", "url", searchURL)
		return false, nil
	}

	// Try each package's resources for a CSV with NOGA data.
	for _, pkg := range searchResp.Result.Results {
		for _, res := range pkg.Resources {
			format := strings.ToUpper(res.Format)
			isCSV := format == "CSV" || strings.HasSuffix(strings.ToLower(res.URL), ".csv")
			if !isCSV {
				continue
			}
			found, n, err := z.downloadAndParseCSV(ctx, res.URL)
			if err != nil {
				z.log.Warn("zefix ckan: resource parse failed",
					"package", pkg.Title, "url", res.URL, "err", err)
				continue
			}
			if found {
				result.Discovered += n
				return true, nil
			}
		}
	}
	return false, nil
}

// downloadAndParseCSV downloads a CSV resource and looks for NOGA 4511 entries.
// Returns (true, n, nil) if a NOGA column was found and n rows were upserted.
// Returns (false, 0, nil) if the CSV has no recognisable NOGA column.
func (z *Zefix) downloadAndParseCSV(ctx context.Context, resourceURL string) (bool, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, resourceURL, nil)
	if err != nil {
		return false, 0, fmt.Errorf("zefix ckan csv: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := z.client.Do(req)
	if err != nil {
		return false, 0, fmt.Errorf("zefix ckan csv: http get: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, 0, fmt.Errorf("zefix ckan csv: HTTP %d", resp.StatusCode)
	}

	reader := csv.NewReader(io.LimitReader(resp.Body, 200<<20)) // 200 MB cap
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	// Read header row.
	headers, err := reader.Read()
	if err != nil {
		return false, 0, fmt.Errorf("zefix ckan csv: read header: %w", err)
	}

	colIdx := make(map[string]int, len(headers))
	for i, h := range headers {
		colIdx[strings.ToLower(strings.TrimSpace(h))] = i
	}

	// Detect NOGA column.
	nogaCol := colByName(colIdx, "noga_code", "noga", "aktivitaet_noga", "activite_noga", "attivita_noga")
	if nogaCol < 0 {
		return false, 0, nil // no NOGA column — not suitable
	}

	// Identify other useful columns.
	uidCol := colByName(colIdx, "uid", "uid_hesg", "company_uid", "unternehmens_uid")
	nameCol := colByName(colIdx, "name", "firmenname", "company_name", "name_de", "bezeichnung")
	cantonCol := colByName(colIdx, "kanton", "canton", "sitz_kanton", "canton_domicile")
	cityCol := colByName(colIdx, "ort", "city", "sitz_ort", "municipality", "gemeinde")
	legalFormCol := colByName(colIdx, "rechtsform", "legal_form", "forme_juridique", "forma_giuridica")

	if uidCol < 0 || nameCol < 0 {
		return false, 0, nil // insufficient columns
	}

	n := 0
	for {
		if ctx.Err() != nil {
			break
		}
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue // skip malformed rows
		}
		if nogaCol >= len(record) || uidCol >= len(record) || nameCol >= len(record) {
			continue
		}

		noga := strings.TrimSpace(record[nogaCol])
		if !strings.HasPrefix(noga, nogaTarget) {
			continue
		}

		uid := normalizeUID(strings.TrimSpace(record[uidCol]))
		name := strings.TrimSpace(record[nameCol])
		if uid == "" || name == "" {
			continue
		}

		entry := &ckanEntry{
			UID:  uid,
			Name: name,
			NOGA: noga,
		}
		if cantonCol >= 0 && cantonCol < len(record) {
			entry.Canton = strings.TrimSpace(record[cantonCol])
		}
		if cityCol >= 0 && cityCol < len(record) {
			entry.City = strings.TrimSpace(record[cityCol])
		}
		if legalFormCol >= 0 && legalFormCol < len(record) {
			entry.LegalForm = strings.TrimSpace(record[legalFormCol])
		}

		if err := z.upsertCKANEntry(ctx, entry); err != nil {
			z.log.Warn("zefix ckan: upsert failed", "uid", uid, "err", err)
			continue
		}
		n++
		metrics.DealersTotal.WithLabelValues(familyID, countryCH).Inc()
	}

	return true, n, nil
}

func (z *Zefix) upsertCKANEntry(ctx context.Context, e *ckanEntry) error {
	now := time.Now().UTC()

	existing, err := z.graph.FindDealerByIdentifier(ctx, kg.IdentifierZefix, e.UID)
	if err != nil {
		return err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     e.Name,
		NormalizedName:    strings.ToLower(e.Name),
		CountryCode:       countryCH,
		Status:            kg.StatusActive,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if e.LegalForm != "" {
		lf := e.LegalForm
		entity.LegalForm = &lf
	}

	if err := z.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	if err := z.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierZefix,
		IdentifierValue: e.UID,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    countryCH,
		SourceFamilies: familyID,
	}
	if e.City != "" {
		city := e.City
		loc.City = &city
	}
	if e.Canton != "" {
		canton := e.Canton
		loc.Region = &canton
	}

	if err := z.graph.AddLocation(ctx, loc); err != nil {
		return err
	}

	uid := e.UID
	return z.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &uid,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// ── Zefix HTML fallback ──────────────────────────────────────────────────────

// zefixEntity is a record parsed from the Zefix search result HTML.
type zefixEntity struct {
	UID       string
	Name      string
	LegalForm string
	Canton    string
}

// runZefixHTML performs keyword searches on zefix.ch and upserts found companies.
func (z *Zefix) runZefixHTML(ctx context.Context, result *runner.SubTechniqueResult) error {
	for _, kw := range automotiveKeywords {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if err := z.limiter.Wait(ctx); err != nil {
			return err
		}

		entities, err := z.searchKeyword(ctx, kw)
		if err != nil {
			z.log.Warn("zefix html: keyword search failed", "keyword", kw, "err", err)
			result.Errors++
			continue
		}

		for i := range entities {
			if err := z.upsertZefixEntity(ctx, &entities[i]); err != nil {
				result.Errors++
				z.log.Warn("zefix html: upsert failed",
					"uid", entities[i].UID, "err", err)
				continue
			}
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryCH).Inc()
		}
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()
	}
	return nil
}

// searchKeyword performs a single keyword search on zefix.ch and returns
// all matching entities parsed from the HTML response.
func (z *Zefix) searchKeyword(ctx context.Context, keyword string) ([]zefixEntity, error) {
	searchURL := z.zefixSearchURL + "?" + url.Values{
		"name":       {keyword},
		"searchType": {"0"},
		"status":     {"ACTIVE"},
	}.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return nil, fmt.Errorf("zefix html: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")

	resp, err := z.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("zefix html: http get: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("zefix html: HTTP %d for keyword %q", resp.StatusCode, keyword)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("zefix html: parse HTML: %w", err)
	}

	return parseSearchResults(doc), nil
}

// parseSearchResults extracts zefixEntity records from the goquery document.
// Probes two layouts:
//   - Layout 1: <table> with tbody rows (classic Zefix table interface)
//   - Layout 2: <ul>/<li> or <div> card layout (newer Zefix SPA shell)
func parseSearchResults(doc *goquery.Document) []zefixEntity {
	var entities []zefixEntity

	// Layout 1: table rows.
	doc.Find("table tbody tr").Each(func(_ int, row *goquery.Selection) {
		cells := row.Find("td")
		if cells.Length() < 2 {
			return
		}
		var e zefixEntity
		cells.Each(func(i int, cell *goquery.Selection) {
			text := strings.TrimSpace(cell.Text())
			switch i {
			case 0:
				e.Name = text
			case 1:
				e.LegalForm = text
			case 2:
				e.Canton = text
			}
		})
		// UID is in the detail-link href: /en/search/entity/list/uid/CHE-NNN.NNN.NNN
		cells.First().Find("a").Each(func(_ int, a *goquery.Selection) {
			if href, ok := a.Attr("href"); ok {
				if uid := uidFromHref(href); uid != "" {
					e.UID = uid
				}
			}
		})
		if e.UID == "" || e.Name == "" {
			return
		}
		entities = append(entities, e)
	})

	// Layout 2: card/list layout (fallback for SPA-wrapped pages).
	if len(entities) == 0 {
		doc.Find("ul.company-list li, div.company-card, div.result-item, li[data-uid]").Each(func(_ int, item *goquery.Selection) {
			var e zefixEntity
			e.Name = strings.TrimSpace(item.Find(".company-name, .name, h3").First().Text())
			e.LegalForm = strings.TrimSpace(item.Find(".legal-form, .rechtsform").First().Text())
			e.Canton = strings.TrimSpace(item.Find(".canton, .kanton").First().Text())
			if uid, exists := item.Attr("data-uid"); exists {
				e.UID = normalizeUID(uid)
			}
			if e.UID == "" {
				item.Find("a").Each(func(_ int, a *goquery.Selection) {
					if href, ok := a.Attr("href"); ok {
						if uid := uidFromHref(href); uid != "" {
							e.UID = uid
						}
					}
				})
			}
			if e.UID == "" || e.Name == "" {
				return
			}
			entities = append(entities, e)
		})
	}

	return entities
}

func (z *Zefix) upsertZefixEntity(ctx context.Context, e *zefixEntity) error {
	now := time.Now().UTC()

	existing, err := z.graph.FindDealerByIdentifier(ctx, kg.IdentifierZefix, e.UID)
	if err != nil {
		return err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     e.Name,
		NormalizedName:    strings.ToLower(e.Name),
		CountryCode:       countryCH,
		Status:            kg.StatusActive,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if e.LegalForm != "" {
		lf := e.LegalForm
		entity.LegalForm = &lf
	}

	if err := z.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	if err := z.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierZefix,
		IdentifierValue: e.UID,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    countryCH,
		SourceFamilies: familyID,
	}
	if e.Canton != "" {
		canton := e.Canton
		loc.Region = &canton
	}
	if err := z.graph.AddLocation(ctx, loc); err != nil {
		return err
	}

	uid := e.UID
	return z.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &uid,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// colByName returns the column index for the first matching name (case-insensitive),
// or -1 if none of the candidates are present.
func colByName(colIdx map[string]int, names ...string) int {
	for _, n := range names {
		if idx, ok := colIdx[n]; ok {
			return idx
		}
	}
	return -1
}

// uidFromHref extracts a CHE UID from a Zefix href such as
// /en/search/entity/list/uid/CHE-123.456.789 or similar patterns.
func uidFromHref(href string) string {
	parts := strings.Split(href, "/")
	for i, p := range parts {
		if strings.ToLower(p) == "uid" && i+1 < len(parts) {
			return normalizeUID(parts[i+1])
		}
	}
	return ""
}

// normalizeUID converts any UID representation to the canonical CHE-NNN.NNN.NNN format.
// Accepts: CHE123456789, CHE-123456789, 123.456.789, CHE-123.456.789, etc.
// Returns "" if the input cannot be resolved to a 9-digit UID.
func normalizeUID(raw string) string {
	s := strings.TrimSpace(raw)
	s = strings.TrimPrefix(s, "CHE-")
	s = strings.TrimPrefix(s, "CHE")
	s = strings.ReplaceAll(s, ".", "")
	s = strings.ReplaceAll(s, "-", "")
	if len(s) != 9 {
		return ""
	}
	return fmt.Sprintf("CHE-%s.%s.%s", s[:3], s[3:6], s[6:])
}
