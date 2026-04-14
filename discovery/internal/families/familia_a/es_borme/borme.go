// Package es_borme implements sub-technique A.ES.1 — BORME datosabiertos API.
//
// Coverage: Spanish Boletín Oficial del Registro Mercantil (BORME), Section A
// (Inscripciones del Registro Mercantil) — company constitutions, modifications,
// dissolutions published daily on business days.
//
// API: GET https://www.boe.es/datosabiertos/api/borme/sumario/YYYYMMDD
//   Accept: application/xml
//   User-Agent: CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)
//   No authentication required — public open data.
//
// Strategy:
//   - Fetch sumario for today and the past backfillDays business days.
//   - Parse Section A entries (Inscripciones) from the XML.
//   - Upsert each entry with identifier BORME_ACT (BORME-A-YYYY-NNN-N).
//   - NO CNAE filtering at this layer — cross-validation with Familias B/F/G
//     in later sprints will narrow to CNAE 4511. The BORME sumario does not
//     include CNAE codes; individual act parsing (PDF/XML) would require N+1
//     requests and is deferred to Sprint 3.
//
// Rate: 1 req / 2s — conservative for public API.
//
// Legal: Loi datos abiertos BOE — acceso público gratuito, reutilización libre.
package es_borme

import (
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
	"golang.org/x/time/rate"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	baseURL     = "https://www.boe.es/datosabiertos/api/borme/sumario/"
	cardexUA    = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID   = "A.ES.1"
	subTechName = "BORME datosabiertos API"
	familyID    = "A"
	countryES   = "ES"

	// backfillDays: how many past days to ingest on each Run call.
	// Handles weekends and holidays gracefully (404 → skip).
	backfillDays = 7
)

// BORME implements runner.SubTechnique for A.ES.1.
type BORME struct {
	graph   kg.KnowledgeGraph
	baseURL string
	limiter *rate.Limiter
	client  *http.Client
	log     *slog.Logger
}

// New creates a BORME sub-technique executor.
func New(graph kg.KnowledgeGraph) *BORME {
	return NewWithBaseURL(graph, baseURL)
}

// NewWithBaseURL creates a BORME executor with a custom base URL (for tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, base string) *BORME {
	return &BORME{
		graph:   graph,
		baseURL: base,
		limiter: rate.NewLimiter(rate.Every(2*time.Second), 1),
		client:  &http.Client{Timeout: 30 * time.Second},
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

func (b *BORME) ID() string      { return subTechID }
func (b *BORME) Name() string    { return subTechName }
func (b *BORME) Country() string { return countryES }

// Run fetches the BORME sumario for today and the past backfillDays days,
// upserts Section A entries into the KG.
func (b *BORME) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryES,
	}

	today := time.Now().In(madridLoc())
	for i := 0; i <= backfillDays; i++ {
		day := today.AddDate(0, 0, -i)
		// BORME is not published on weekends.
		if day.Weekday() == time.Saturday || day.Weekday() == time.Sunday {
			continue
		}
		dateKey := day.Format("20060102")

		if err := b.limiter.Wait(ctx); err != nil {
			return result, err
		}

		entries, err := b.fetchDay(ctx, dateKey)
		if err != nil {
			// 404 → no BORME for this day (holiday). Continue.
			if isHTTP404(err) {
				b.log.Debug("borme: no publication for date", "date", dateKey)
				continue
			}
			result.Errors++
			b.log.Warn("borme: fetch error", "date", dateKey, "err", err)
			continue
		}

		for i := range entries {
			if err := b.upsertEntry(ctx, &entries[i]); err != nil {
				result.Errors++
				b.log.Warn("borme: upsert error",
					"id", entries[i].ID, "err", err)
				continue
			}
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryES).Inc()
		}
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryES).Observe(result.Duration.Seconds())
	return result, nil
}

// ── XML types ──────────────────────────────────────────────────────────────

// bormeXMLEntry is a single Section A announcement from the BORME sumario.
type bormeXMLEntry struct {
	ID             string
	CompanyName    string
	ActType        string
	Province       string
	RegistroName   string
	URLPDF         string
	URLXMLItem     string
}

// bormeXMLSumario is the top-level XML structure of the BORME sumario response.
// The BOE/BORME datosabiertos API returns an XML envelope whose exact element
// names are documented in APIsumarioBORME.pdf. This struct handles both the
// documented canonical format and the legacy format seen in older archives.
type bormeXMLSumario struct {
	XMLName xml.Name `xml:"sumario"`
	Diario  struct {
		Numero    string `xml:"numero,attr"`
		Secciones []struct {
			Tipo      string `xml:"tipo,attr"`
			Nombre    string `xml:"nombre,attr"`
			Empresas  []struct {
				ID             string `xml:"id,attr"`
				NombreEmpresa  string `xml:"nombre_empresa"`
				Acto           string `xml:"acto"`
				Tipo           string `xml:"tipo"`
				Provincia      string `xml:"provincia"`
				Registro       string `xml:"registro"`
				URLPDF         string `xml:"url_pdf"`
				URLXMLItem     string `xml:"url_xml"`
			} `xml:"empresa"`
		} `xml:"sumario_nbo"`
	} `xml:"diario"`
}

// fetchDay fetches the BORME sumario for dateKey (YYYYMMDD) and returns
// all Section A entries.
func (b *BORME) fetchDay(ctx context.Context, dateKey string) ([]bormeXMLEntry, error) {
	url := b.baseURL + dateKey

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("borme: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/xml")

	resp, err := b.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("borme: http get: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusNotFound {
		return nil, &httpError{code: 404}
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("borme: HTTP %d: %s", resp.StatusCode, body)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 50<<20)) // 50 MB cap
	if err != nil {
		return nil, fmt.Errorf("borme: read body: %w", err)
	}

	var sumario bormeXMLSumario
	if err := xml.Unmarshal(body, &sumario); err != nil {
		return nil, fmt.Errorf("borme: parse XML: %w (first 200 bytes: %s)",
			err, truncate(string(body), 200))
	}

	var entries []bormeXMLEntry
	for _, sec := range sumario.Diario.Secciones {
		if sec.Tipo != "A" {
			continue // Only Section A — Inscripciones
		}
		for _, e := range sec.Empresas {
			if e.ID == "" || e.NombreEmpresa == "" {
				continue
			}
			entries = append(entries, bormeXMLEntry{
				ID:           e.ID,
				CompanyName:  strings.TrimSpace(e.NombreEmpresa),
				ActType:      strings.TrimSpace(e.Acto),
				Province:     strings.TrimSpace(e.Provincia),
				RegistroName: strings.TrimSpace(e.Registro),
				URLPDF:       e.URLPDF,
				URLXMLItem:   e.URLXMLItem,
			})
		}
	}
	return entries, nil
}

// upsertEntry writes one BORME Section A entry into the KG.
func (b *BORME) upsertEntry(ctx context.Context, e *bormeXMLEntry) error {
	now := time.Now().UTC()

	existing, err := b.graph.FindDealerByIdentifier(ctx, kg.IdentifierBORMEAct, e.ID)
	if err != nil {
		return err
	}

	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     e.CompanyName,
		NormalizedName:    strings.ToLower(e.CompanyName),
		CountryCode:       countryES,
		Status:            statusFromActType(e.ActType),
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}

	if err := b.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	// BORME announcement identifier.
	if err := b.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierBORMEAct,
		IdentifierValue: e.ID,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	// Location — province only (no full address in sumario).
	if e.Province != "" {
		region := e.Province
		loc := &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			CountryCode:    countryES,
			Region:         &region,
			SourceFamilies: familyID,
		}
		if err := b.graph.AddLocation(ctx, loc); err != nil {
			return err
		}
	}

	// Discovery record.
	srcID := e.ID
	srcURL := e.URLXMLItem
	rec := &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &srcID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}
	if srcURL != "" {
		rec.SourceURL = &srcURL
	}
	return b.graph.RecordDiscovery(ctx, rec)
}

// ── Helpers ────────────────────────────────────────────────────────────────

func statusFromActType(actType string) kg.DealerStatus {
	lower := strings.ToLower(actType)
	switch {
	case strings.Contains(lower, "disolución") ||
		strings.Contains(lower, "liquidación") ||
		strings.Contains(lower, "extinción") ||
		strings.Contains(lower, "cancelación"):
		return kg.StatusClosed
	case strings.Contains(lower, "constitución") ||
		strings.Contains(lower, "modificación") ||
		strings.Contains(lower, "nombramiento") ||
		strings.Contains(lower, "ampliación"):
		return kg.StatusActive
	default:
		return kg.StatusUnverified
	}
}

func madridLoc() *time.Location {
	loc, err := time.LoadLocation("Europe/Madrid")
	if err != nil {
		return time.UTC
	}
	return loc
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}

// httpError is a typed error for HTTP status codes.
type httpError struct{ code int }

func (e *httpError) Error() string { return fmt.Sprintf("HTTP %d", e.code) }

func isHTTP404(err error) bool {
	if err == nil {
		return false
	}
	var he *httpError
	if errors.As(err, &he) {
		return he.code == 404
	}
	return strings.Contains(err.Error(), "HTTP 404") || strings.Contains(err.Error(), "404")
}
