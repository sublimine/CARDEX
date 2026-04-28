// Package fr_sirene implements sub-technique A.FR.1 — INSEE Sirene API.
//
// Coverage: All French establishments (établissements) with APE code 4511Z
// (sale of cars and light motor vehicles) and ACTIVE administrative status.
//
// API: GET https://api.insee.fr/entreprises/sirene/V3/siret
//   q=activitePrincipaleEtablissement:45.11Z AND etatAdministratifEtablissement:A
//   Authorization: Bearer <INSEE_TOKEN>
//   Rate limit: 30 req/min (free tier) — config uses 25 to stay safe.
//
// Legal basis: Loi République numérique — open data.
// Identification: CardexBot/1.0 UA on every request.
package fr_sirene

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
	"unicode"

	"github.com/oklog/ulid/v2"
	"golang.org/x/time/rate"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	baseURL      = "https://api.insee.fr/entreprises/sirene/V3/siret"
	pageSize     = 1000
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID    = "A.FR.1"
	subTechName  = "INSEE Sirene API"
	familyID     = "A"
	countryFR    = "FR"
	apeCode      = "45.11Z"
	activeStatus = "A"
)

// Sirene implements the runner.SubTechnique interface for A.FR.1.
type Sirene struct {
	graph   kg.KnowledgeGraph
	token   string
	limiter *rate.Limiter
	client  *http.Client
	apiURL  string // overridable for testing
}

// New creates a new Sirene sub-technique executor.
// ratePerMin: requests per minute ceiling (free tier = 30; use 25 conservatively).
func New(graph kg.KnowledgeGraph, token string, ratePerMin int) *Sirene {
	return NewWithBaseURL(graph, token, ratePerMin, baseURL)
}

// NewWithBaseURL creates a Sirene executor with a custom API base URL.
// Intended for testing with httptest.Server; production code should use New.
func NewWithBaseURL(graph kg.KnowledgeGraph, token string, ratePerMin int, apiURL string) *Sirene {
	rl := rate.NewLimiter(rate.Every(time.Minute/time.Duration(ratePerMin)), 1)
	return &Sirene{
		graph:   graph,
		token:   token,
		limiter: rl,
		apiURL:  apiURL,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (s *Sirene) ID() string      { return subTechID }
func (s *Sirene) Name() string    { return subTechName }
func (s *Sirene) Country() string { return countryFR }

// HealthCheck issues a probe request (nombre=1) to verify that the INSEE API
// is reachable and the token is accepted. Returns nil if healthy.
func (s *Sirene) HealthCheck(ctx context.Context) error {
	_, err := s.fetchPage(ctx, 0)
	if err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("sirene.HealthCheck: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}

// Run paginates through the full INSEE Sirene result set and upserts every
// matching establishment into the KG.
func (s *Sirene) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryFR,
	}

	var cursor int
	for {
		if err := ctx.Err(); err != nil {
			return result, err
		}

		page, err := s.fetchPage(ctx, cursor)
		if err != nil {
			result.Errors++
			metrics.SubTechniqueRequests.WithLabelValues(subTechID, "5xx").Inc()
			return result, fmt.Errorf("sirene.Run page %d: %w", cursor, err)
		}
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()

		if len(page.Etablissements) == 0 {
			break
		}

		for i := range page.Etablissements {
			if err := s.upsertEtablissement(ctx, &page.Etablissements[i]); err != nil {
				result.Errors++
				continue
			}
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryFR).Inc()
		}

		if cursor+len(page.Etablissements) >= page.Header.Total {
			break
		}
		cursor += len(page.Etablissements)
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryFR).Observe(result.Duration.Seconds())
	return result, nil
}

// ─── INSEE API response types ──────────────────────────────────────────────

type sirenePage struct {
	Header struct {
		Total  int `json:"total"`
		Debut  int `json:"debut"`
		Nombre int `json:"nombre"`
	} `json:"header"`
	Etablissements []etablissement `json:"etablissements"`
}

type etablissement struct {
	Siret                     string `json:"siret"`
	Siren                     string `json:"siren"`
	UniteLegale               uniteLegale `json:"uniteLegale"`
	AdresseEtablissement      adresseEtablissement `json:"adresseEtablissement"`
	PeriodeEtablissement      []periodeEtablissement `json:"periodesEtablissement"`
	DateCreationEtablissement string `json:"dateCreationEtablissement"`
}

type uniteLegale struct {
	DenominationUniteLegale             string `json:"denominationUniteLegale"`
	NomUniteLegale                      string `json:"nomUniteLegale"`
	PrenomUsuelUniteLegale              string `json:"prenomUsuelUniteLegale"`
	CategorieJuridiqueUniteLegale       string `json:"categorieJuridiqueUniteLegale"`
	EtatAdministratifUniteLegale        string `json:"etatAdministratifUniteLegale"`
}

type adresseEtablissement struct {
	NumeroVoieEtablissement   string `json:"numeroVoieEtablissement"`
	TypeVoieEtablissement     string `json:"typeVoieEtablissement"`
	LibelleVoieEtablissement  string `json:"libelleVoieEtablissement"`
	CodePostalEtablissement   string `json:"codePostalEtablissement"`
	LibelleCommuneEtablissement string `json:"libelleCommuneEtablissement"`
	LibelleRegionEtablissement string `json:"libelleRegionEtablissement"`
}

type periodeEtablissement struct {
	EtatAdministratifEtablissement string `json:"etatAdministratifEtablissement"`
	ActivitePrincipaleEtablissement string `json:"activitePrincipaleEtablissement"`
}

// ─── Persistence helpers ───────────────────────────────────────────────────

func (s *Sirene) upsertEtablissement(ctx context.Context, e *etablissement) error {
	now := time.Now().UTC()
	dealerID := ulid.Make().String()

	// Check whether this SIRET is already in the KG.
	existing, err := s.graph.FindDealerByIdentifier(ctx, kg.IdentifierSIRET, e.Siret)
	if err != nil {
		return err
	}
	if existing != "" {
		dealerID = existing
	}

	name := canonicalName(e)
	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    normalizeName(name),
		CountryCode:       countryFR,
		Status:            kg.StatusActive,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}

	if lf := legalForm(e.UniteLegale.CategorieJuridiqueUniteLegale); lf != "" {
		entity.LegalForm = &lf
	}

	if err := s.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	// Add SIRET identifier
	siretID := &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierSIRET,
		IdentifierValue: e.Siret,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}
	if err := s.graph.AddIdentifier(ctx, siretID); err != nil {
		return err
	}

	// Add SIREN identifier (unit légale level)
	if e.Siren != "" && e.Siren != e.Siret {
		sirenID := &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierSIREN,
			IdentifierValue: e.Siren,
			SourceFamily:    familyID,
			ValidStatus:     "VALID",
		}
		_ = s.graph.AddIdentifier(ctx, sirenID) // ignore duplicate
	}

	// Add location
	addr := e.AdresseEtablissement
	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    countryFR,
		SourceFamilies: familyID,
	}
	if addr.CodePostalEtablissement != "" {
		loc.PostalCode = &addr.CodePostalEtablissement
	}
	if addr.LibelleCommuneEtablissement != "" {
		loc.City = &addr.LibelleCommuneEtablissement
	}
	if addr.LibelleRegionEtablissement != "" {
		loc.Region = &addr.LibelleRegionEtablissement
	}
	line1 := buildAddressLine1(addr)
	if line1 != "" {
		loc.AddressLine1 = &line1
	}
	if err := s.graph.AddLocation(ctx, loc); err != nil {
		return err
	}

	// Audit record
	siretRef := e.Siret
	rec := &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &siretRef,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}
	return s.graph.RecordDiscovery(ctx, rec)
}

// ─── HTTP helpers ──────────────────────────────────────────────────────────

func (s *Sirene) fetchPage(ctx context.Context, debut int) (*sirenePage, error) {
	if err := s.limiter.Wait(ctx); err != nil {
		return nil, err
	}

	q := fmt.Sprintf(
		`activitePrincipaleEtablissement:%s AND etatAdministratifEtablissement:%s`,
		apeCode, activeStatus,
	)
	params := url.Values{
		"q":      {q},
		"nombre": {fmt.Sprintf("%d", pageSize)},
		"debut":  {fmt.Sprintf("%d", debut)},
	}
	reqURL := s.apiURL + "?" + params.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("sirene: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")
	if s.token != "" {
		req.Header.Set("Authorization", "Bearer "+s.token)
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("sirene: http do: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 10<<20)) // 10 MB cap
	if err != nil {
		return nil, fmt.Errorf("sirene: read body: %w", err)
	}

	if resp.StatusCode == http.StatusTooManyRequests {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "429").Inc()
		return nil, fmt.Errorf("sirene: 429 rate limited")
	}
	if resp.StatusCode != http.StatusOK {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()
		return nil, fmt.Errorf("sirene: HTTP %d: %s", resp.StatusCode, truncate(string(body), 200))
	}

	var page sirenePage
	if err := json.Unmarshal(body, &page); err != nil {
		return nil, fmt.Errorf("sirene: decode JSON: %w", err)
	}
	return &page, nil
}

// ─── String helpers ────────────────────────────────────────────────────────

func canonicalName(e *etablissement) string {
	if d := e.UniteLegale.DenominationUniteLegale; d != "" {
		return d
	}
	parts := []string{
		e.UniteLegale.PrenomUsuelUniteLegale,
		e.UniteLegale.NomUniteLegale,
	}
	var joined []string
	for _, p := range parts {
		if p != "" {
			joined = append(joined, p)
		}
	}
	if len(joined) > 0 {
		return strings.Join(joined, " ")
	}
	return "UNKNOWN_" + e.Siret
}

func normalizeName(name string) string {
	// lowercase + strip accents (basic fold — full Unicode normalization deferred)
	return strings.Map(func(r rune) rune {
		return unicode.ToLower(r)
	}, name)
}

// legalForm maps the INSEE CJ code prefix to a human-readable legal form.
// Only top-level codes relevant to automotive dealers are handled.
func legalForm(cj string) string {
	if len(cj) < 2 {
		return ""
	}
	switch cj[:2] {
	case "57":
		return "SARL"
	case "55":
		return "SA"
	case "52":
		return "SAS"
	case "10":
		return "EI" // entrepreneur individuel
	case "21":
		return "INDIVISION"
	default:
		return ""
	}
}

func buildAddressLine1(addr adresseEtablissement) string {
	parts := []string{
		addr.NumeroVoieEtablissement,
		addr.TypeVoieEtablissement,
		addr.LibelleVoieEtablissement,
	}
	var out []string
	for _, p := range parts {
		if p != "" {
			out = append(out, p)
		}
	}
	return strings.Join(out, " ")
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}
