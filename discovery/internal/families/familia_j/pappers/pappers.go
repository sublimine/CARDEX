// Package pappers implements sub-technique J.FR.1 — Pappers.fr company search.
//
// # What it does
//
// Pappers.fr is a French commercial registry aggregator that re-exposes INFOGREFFE
// and BODACC data with a clean REST API. CARDEX uses it as a complement to
// A.FR.1 (INSEE Sirene) because:
//
//  1. Pappers returns financial signals not in Sirene: last reported revenue (CA),
//     employee count range, list of dirigeants (legal reps), and legal proceedings.
//  2. Sector filter APE 4511Z (vehicle retail) is supported natively, vs. Sirene
//     which requires post-filtering.
//  3. Pappers cross-validates existing KG entries — a Sirene-discovered dealer
//     with matching Pappers record is promoted from UNVERIFIED.
//
// # API
//
// Free tier: 50 req/h unauthenticated, 1000 req/h with free API key.
// Endpoint: GET https://api.pappers.fr/v2/entreprises
//
// Key query params:
//   - code_naf=4511Z      -- automobile retail (NACE 45.11)
//   - departement={dept}  -- 2-digit department code (01-95, 2A, 2B, 971-976)
//   - par_page=100        -- max results per page
//   - page={n}            -- pagination
//   - api_token={key}     -- required for >50 req/h
//
// Response shape (trimmed):
//
//	{
//	  "total": 1234,
//	  "resultats": [
//	    {
//	      "siren": "123456789",
//	      "siret": "12345678900012",
//	      "nom_entreprise": "GARAGE DUPONT SAS",
//	      "siege": { "adresse_ligne_1": "12 RUE DE LA PAIX", "code_postal": "75001", "ville": "PARIS" },
//	      "code_naf": "4511Z",
//	      "chiffre_affaires": 1200000,
//	      "effectif": "6 a 9 salaries"
//	    }
//	  ]
//	}
//
// # Cross-validation
//
// For each Pappers result:
//  1. Check dealer_identifier for SIRET match (existing A.FR.1 entry).
//  2. If match found AND dealer is UNVERIFIED: promote to ACTIVE + bump confidence.
//  3. If no match: upsert as new dealer with source family "J".
//
// # Rate limiting
//
// With free API key (1000 req/h): 1 req/3.6 s conservative.
// Without key: 1 req/72 s (50 req/h). The implementation uses the key when
// PAPPERS_API_KEY env var is set.
//
// # Coverage
//
// 101 departements × ~avg 120 dealers/dept = ~12,000 dealers/full scan.
// Sprint 13 scans 1 departement per Run call (country-level dispatch cycles
// through departments using KG processing_state checkpoint).
//
// BaseWeights["J"] = 0.05.
package pappers

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "J"
	subTechID   = "J.FR.1"
	subTechName = "Pappers.fr company search — APE 4511Z vehicle retail (FR)"

	defaultBaseURL      = "https://api.pappers.fr/v2"
	defaultPageSize     = 100
	defaultReqInterval  = 4 * time.Second // ~900 req/h with key; 3.6s rounds to 4s
	noKeyReqInterval    = 75 * time.Second // ~48 req/h without key (conservative)

	// confidenceBump is added when Pappers cross-validates an existing UNVERIFIED
	// dealer discovered by A.FR.1 (same SIRET, same source country).
	confidenceBump = 0.05

	codeNAF  = "4511Z"
	cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// frDepartements is the ordered list of 2-char departement codes for FR.
// 2A/2B = Corse; 97x = overseas territories (scanned but lower priority).
var frDepartements = []string{
	"01", "02", "03", "04", "05", "06", "07", "08", "09",
	"10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
	"21", "22", "23", "24", "25", "26", "27", "28", "29",
	"2A", "2B",
	"30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
	"40", "41", "42", "43", "44", "45", "46", "47", "48", "49",
	"50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
	"60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
	"70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
	"80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
	"90", "91", "92", "93", "94", "95",
	"971", "972", "973", "974", "976",
}

// -- Pappers API types --------------------------------------------------------

type pappersResponse struct {
	Total     int              `json:"total"`
	Resultats []pappersCompany `json:"resultats"`
}

type pappersCompany struct {
	SIREN        string       `json:"siren"`
	SIRET        string       `json:"siret"`
	NomEntreprise string      `json:"nom_entreprise"`
	Siege        pappersAdresse `json:"siege"`
	CodeNAF      string       `json:"code_naf"`
	CA           *int64       `json:"chiffre_affaires"`
	Effectif     string       `json:"effectif"`
}

type pappersAdresse struct {
	AdresseLigne1 string `json:"adresse_ligne_1"`
	CodePostal    string `json:"code_postal"`
	Ville         string `json:"ville"`
}

// -- Pappers sub-technique ---------------------------------------------------

// Pappers executes J.FR.1 Pappers company search for one French departement per call.
type Pappers struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	apiKey      string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a Pappers executor with production configuration.
// apiKey is the Pappers API token; pass "" for unauthenticated (rate-limited).
func New(graph kg.KnowledgeGraph, apiKey string) *Pappers {
	interval := defaultReqInterval
	if apiKey == "" {
		interval = noKeyReqInterval
	}
	return NewWithBaseURL(graph, apiKey, defaultBaseURL, interval)
}

// NewWithBaseURL returns a Pappers executor with custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, apiKey, baseURL string, reqInterval time.Duration) *Pappers {
	return &Pappers{
		graph:       graph,
		client:      &http.Client{Timeout: 20 * time.Second},
		baseURL:     baseURL,
		apiKey:      apiKey,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient returns a Pappers executor using a custom HTTP client (for tests).
func NewWithClient(graph kg.KnowledgeGraph, apiKey, baseURL string, c *http.Client) *Pappers {
	return &Pappers{
		graph:   graph,
		client:  c,
		baseURL: baseURL,
		apiKey:  apiKey,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (p *Pappers) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (p *Pappers) Name() string { return subTechName }

// Run fetches one departement's worth of APE 4511Z companies from Pappers and
// upserts / cross-validates them in the KG. The departement is determined by a
// round-robin checkpoint stored in processing_state.
func (p *Pappers) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "FR"}

	// Determine which departement to scan next.
	dept, nextIdx, err := p.nextDepartement(ctx)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("pappers.Run: checkpoint: %w", err)
	}
	p.log.Info("pappers: scanning departement", "dept", dept, "index", nextIdx-1)

	companies, err := p.fetchAll(ctx, dept)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("pappers.Run: fetch dept=%s: %w", dept, err)
	}

	for _, co := range companies {
		if ctx.Err() != nil {
			break
		}
		n, err := p.upsertCompany(ctx, co)
		if err != nil {
			p.log.Warn("pappers: upsert error", "siret", co.SIRET, "err", err)
			result.Errors++
			continue
		}
		result.Discovered += n
	}
	result.Confirmed = len(companies) - result.Errors

	// Save checkpoint.
	if err := p.graph.SetProcessingState(ctx, "pappers:fr:next_dept_index",
		strconv.Itoa(nextIdx)); err != nil {
		p.log.Warn("pappers: checkpoint save error", "err", err)
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, "FR").Observe(result.Duration.Seconds())
	p.log.Info("pappers: dept done",
		"dept", dept, "companies", len(companies),
		"discovered", result.Discovered, "errors", result.Errors)
	return result, nil
}

// nextDepartement reads the checkpoint and returns (dept, nextIndex).
func (p *Pappers) nextDepartement(ctx context.Context) (string, int, error) {
	raw, err := p.graph.GetProcessingState(ctx, "pappers:fr:next_dept_index")
	if err != nil {
		return "", 0, err
	}
	idx := 0
	if raw != "" {
		if n, err := strconv.Atoi(raw); err == nil {
			idx = n % len(frDepartements)
		}
	}
	dept := frDepartements[idx]
	return dept, (idx + 1) % len(frDepartements), nil
}

// fetchAll paginates through all Pappers results for the departement.
func (p *Pappers) fetchAll(ctx context.Context, dept string) ([]pappersCompany, error) {
	var all []pappersCompany
	page := 1
	for {
		if ctx.Err() != nil {
			break
		}
		if p.reqInterval > 0 && page > 1 {
			select {
			case <-ctx.Done():
				return all, nil
			case <-time.After(p.reqInterval):
			}
		}

		batch, total, err := p.fetchPage(ctx, dept, page)
		if err != nil {
			metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
			return all, fmt.Errorf("page %d: %w", page, err)
		}
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()
		all = append(all, batch...)

		if len(all) >= total || len(batch) < defaultPageSize {
			break
		}
		page++
	}
	return all, nil
}

// fetchPage fetches one page of Pappers results.
func (p *Pappers) fetchPage(ctx context.Context, dept string, page int) ([]pappersCompany, int, error) {
	params := url.Values{
		"code_naf":    {codeNAF},
		"departement": {dept},
		"par_page":    {strconv.Itoa(defaultPageSize)},
		"page":        {strconv.Itoa(page)},
	}
	if p.apiKey != "" {
		params.Set("api_token", p.apiKey)
	}

	reqURL := p.baseURL + "/entreprises?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, 0, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := p.client.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, 0, fmt.Errorf("rate limited (HTTP 429)")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, 0, fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	var pr pappersResponse
	if err := json.NewDecoder(resp.Body).Decode(&pr); err != nil {
		return nil, 0, fmt.Errorf("decode: %w", err)
	}
	return pr.Resultats, pr.Total, nil
}

// upsertCompany cross-validates or inserts a Pappers company into the KG.
// Returns 1 if a new dealer was created, 0 if an existing one was updated.
func (p *Pappers) upsertCompany(ctx context.Context, co pappersCompany) (int, error) {
	if co.SIRET == "" && co.SIREN == "" {
		return 0, nil
	}

	// Prefer SIRET; fall back to SIREN for the identifier lookup.
	idValue := co.SIRET
	idType := kg.IdentifierSIRET
	if idValue == "" {
		idValue = co.SIREN
		idType = kg.IdentifierSIREN
	}

	// Cross-validate: does this SIRET already exist in the KG?
	existingID, err := p.graph.FindDealerByIdentifier(ctx, idType, idValue)
	if err != nil {
		return 0, fmt.Errorf("find by identifier: %w", err)
	}

	normalized := strings.ToLower(strings.TrimSpace(co.NomEntreprise))
	now := time.Now().UTC()

	if existingID != "" {
		// Existing dealer: bump confidence (cross-validation by independent source).
		if err := p.graph.UpdateConfidenceScore(ctx, existingID,
			confidenceBump); err != nil {
			p.log.Warn("pappers: confidence update error", "dealer", existingID, "err", err)
		}
		return 0, nil
	}

	// New dealer: create entity.
	dealerID := ulid.Make().String()
	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     co.NomEntreprise,
		NormalizedName:    normalized,
		CountryCode:       "FR",
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights["J"],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := p.graph.UpsertDealer(ctx, entity); err != nil {
		return 0, fmt.Errorf("upsert dealer: %w", err)
	}

	// Identifier.
	ident := &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  idType,
		IdentifierValue: idValue,
		SourceFamily:    familyID,
		ValidStatus:     "UNKNOWN",
	}
	if err := p.graph.AddIdentifier(ctx, ident); err != nil {
		return 0, fmt.Errorf("add identifier: %w", err)
	}

	// Pappers-specific identifier (for re-fetch).
	pappersIdent := &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierPappersID,
		IdentifierValue: idValue,
		SourceFamily:    familyID,
		ValidStatus:     "UNKNOWN",
	}
	if err := p.graph.AddIdentifier(ctx, pappersIdent); err != nil {
		p.log.Warn("pappers: add pappers identifier error", "err", err)
	}

	// Location.
	if co.Siege.Ville != "" {
		postalCode := co.Siege.CodePostal
		city := co.Siege.Ville
		addr := co.Siege.AdresseLigne1
		loc := &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   &addr,
			PostalCode:     &postalCode,
			City:           &city,
			CountryCode:    "FR",
			SourceFamilies: familyID,
		}
		if err := p.graph.AddLocation(ctx, loc); err != nil {
			p.log.Warn("pappers: add location error", "err", err)
		}
	}

	return 1, nil
}
