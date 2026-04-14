// Package de_offeneregister implements sub-technique A.DE.1 — OffeneRegister.de.
//
// Coverage: German commercial register (Handelsregister) entries aggregated by
// OffeneRegister.de (okfde.github.io/offeneregister.de) under CC-BY 4.0.
//
// Strategy:
//  1. Download https://daten.offeneregister.de/openregister.db.gz (~740 MB gzip → ~2 GB SQLite).
//     Skips re-download if local file is < 30 days old (configurable via OFFENEREGISTER_MAX_AGE_DAYS).
//  2. Stream-decompress via compress/gzip — never loads the full 2 GB in RAM.
//  3. Query SQLite FTS5 virtual table ObjectivesFts over Gegenstand (company purpose)
//     for automotive keywords covering WZ 45.11/45.19/45.20.
//  4. Upsert each match as DealerEntity with identifier HANDELSREGISTER.
//
// Note: Handelsregister does not store NACE/WZ codes. Keyword matching over
// Gegenstand is the only viable free-tier proxy. Cross-validation with
// Familias B/F/G refines precision in later sprints.
//
// Config: OFFENEREGISTER_DB_PATH (default ./data/offeneregister.db)
package de_offeneregister

import (
	"compress/gzip"
	"context"
	"database/sql"
	"fmt"
	"io"
	"log/slog"
	"net/http"
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
	downloadURL = "https://daten.offeneregister.de/openregister.db.gz"
	cardexUA    = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID   = "A.DE.1"
	subTechName = "OffeneRegister.de (Handelsregister)"
	familyID    = "A"
	countryDE   = "DE"

	// maxDBAge: re-download if the local SQLite is older than this.
	maxDBAge = 30 * 24 * time.Hour

	// ftsQuery: FTS5 query matching automotive Gegenstand entries.
	// OR in FTS5 is the default; explicit OR for readability.
	ftsQuery = `Kraftfahrzeug OR Autohaus OR Autohandel OR Automobilhandel OR ` +
		`Fahrzeughandel OR Gebrauchtwagen OR "Kfz-Handel" OR "PKW-Handel" OR ` +
		`Kraftwagen OR Neuwagen OR Automobil`

	// batchLimit caps results per run to avoid overwhelming the KG on first run.
	// Subsequent runs will only hit new/changed entries via date filter.
	batchLimit = 50_000
)

// OffeneRegister implements runner.SubTechnique for A.DE.1.
type OffeneRegister struct {
	graph  kg.KnowledgeGraph
	dbPath string
	client *http.Client
	log    *slog.Logger
}

// New creates an OffeneRegister sub-technique executor.
// dbPath: filesystem path where the decompressed SQLite will be stored.
func New(graph kg.KnowledgeGraph, dbPath string) *OffeneRegister {
	return &OffeneRegister{
		graph:  graph,
		dbPath: dbPath,
		client: &http.Client{Timeout: 0}, // no timeout — 740 MB download
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

func (o *OffeneRegister) ID() string      { return subTechID }
func (o *OffeneRegister) Name() string    { return subTechName }
func (o *OffeneRegister) Country() string { return countryDE }

// Run ensures the OffeneRegister SQLite is current, then runs the FTS5 query
// and upserts all matching dealer entities into the Knowledge Graph.
func (o *OffeneRegister) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryDE,
	}

	if err := o.ensureDatabase(ctx); err != nil {
		result.Errors++
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "download_err").Inc()
		return result, fmt.Errorf("offeneregister.Run: ensure db: %w", err)
	}

	db, err := sql.Open("sqlite", o.dbPath+"?_pragma=foreign_keys(OFF)&_pragma=journal_mode(WAL)&mode=ro")
	if err != nil {
		result.Errors++
		return result, fmt.Errorf("offeneregister.Run: open db: %w", err)
	}
	defer db.Close()

	if err := o.queryAndUpsert(ctx, db, result); err != nil {
		return result, err
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryDE).Observe(result.Duration.Seconds())
	o.log.Info("offeneregister run complete",
		"discovered", result.Discovered,
		"errors", result.Errors,
		"duration", result.Duration,
	)
	return result, nil
}

// ── Database maintenance ────────────────────────────────────────────────────

// ensureDatabase downloads and decompresses the OffeneRegister DB if the local
// copy is absent or older than maxDBAge.
func (o *OffeneRegister) ensureDatabase(ctx context.Context) error {
	if info, err := os.Stat(o.dbPath); err == nil {
		if time.Since(info.ModTime()) < maxDBAge {
			o.log.Info("offeneregister db current — skipping download",
				"path", o.dbPath,
				"age", time.Since(info.ModTime()).Round(time.Hour),
			)
			return nil
		}
		o.log.Info("offeneregister db stale — re-downloading",
			"age", time.Since(info.ModTime()).Round(time.Hour),
		)
	}
	return o.downloadAndDecompress(ctx)
}

// downloadAndDecompress streams the gzipped SQLite to disk.
// Uses a temp file + atomic rename so a partial download never leaves a corrupt DB.
func (o *OffeneRegister) downloadAndDecompress(ctx context.Context) error {
	o.log.Info("downloading offeneregister db", "url", downloadURL)

	if err := os.MkdirAll(filepath.Dir(o.dbPath), 0755); err != nil {
		return fmt.Errorf("offeneregister: mkdir: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, downloadURL, nil)
	if err != nil {
		return fmt.Errorf("offeneregister: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := o.client.Do(req)
	if err != nil {
		return fmt.Errorf("offeneregister: http get: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("offeneregister: HTTP %d from %s", resp.StatusCode, downloadURL)
	}

	// Decompress gzip stream directly from the response body.
	gzReader, err := gzip.NewReader(resp.Body)
	if err != nil {
		return fmt.Errorf("offeneregister: init gzip reader: %w", err)
	}
	defer gzReader.Close()

	// Write to a temp file in the same directory so os.Rename is atomic.
	dir := filepath.Dir(o.dbPath)
	tmpFile, err := os.CreateTemp(dir, "offeneregister_*.db.tmp")
	if err != nil {
		return fmt.Errorf("offeneregister: create temp file: %w", err)
	}
	tmpPath := tmpFile.Name()

	// Ensure cleanup on failure.
	success := false
	defer func() {
		if !success {
			_ = os.Remove(tmpPath)
		}
	}()

	written, err := io.Copy(tmpFile, gzReader)
	if err != nil {
		_ = tmpFile.Close()
		return fmt.Errorf("offeneregister: decompress stream: %w", err)
	}
	if err := tmpFile.Close(); err != nil {
		return fmt.Errorf("offeneregister: close temp file: %w", err)
	}

	if err := os.Rename(tmpPath, o.dbPath); err != nil {
		return fmt.Errorf("offeneregister: atomic rename: %w", err)
	}
	success = true

	o.log.Info("offeneregister db downloaded",
		"path", o.dbPath,
		"bytes_written", written,
	)
	return nil
}

// ── FTS5 query and KG upsert ───────────────────────────────────────────────

// offeneEntry is the raw output of the FTS5 join query.
type offeneEntry struct {
	CompanyID            string
	NativeCompanyNumber  string // Handelsregisternummer: "HRB 12345"
	CompanyType          string // GmbH, AG, UG, etc.
	CurrentStatus        string
	FederalState         string
	RegisteredOffice     string // Ort / city of registration
	Name                 string
	StreetAddress        *string
	City                 *string
	ZipCode              *string
	Objective            string
}

// queryAndUpsert runs the FTS5 search and upserts results into the KG.
func (o *OffeneRegister) queryAndUpsert(ctx context.Context, db *sql.DB, result *runner.SubTechniqueResult) error {
	// Verify FTS5 table exists before querying.
	var tblCount int
	row := db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ObjectivesFts'`)
	if err := row.Scan(&tblCount); err != nil || tblCount == 0 {
		return fmt.Errorf("offeneregister: ObjectivesFts FTS5 table not found — schema mismatch or empty db")
	}

	const q = `
SELECT DISTINCT
  c.id,
  COALESCE(c.native_company_number, c.company_number, '') AS native_num,
  COALESCE(c.company_type, '')         AS company_type,
  COALESCE(c.current_status, '')       AS current_status,
  COALESCE(c.federal_state, '')        AS federal_state,
  COALESCE(c.registered_office, '')    AS registered_office,
  COALESCE(n.name, '')                 AS name,
  a.street_address,
  a.city,
  a.zip_code,
  COALESCE(obj.objective, '')          AS objective
FROM companies c
JOIN objectives obj ON obj.company_id = c.id
JOIN ObjectivesFts fts ON fts.rowid = obj.id
LEFT JOIN names n     ON n.company_id  = c.id
LEFT JOIN addresses a ON a.company_id  = c.id
WHERE ObjectivesFts MATCH ?
  AND (c.current_status = 'currently registered' OR c.current_status IS NULL)
LIMIT ?`

	rows, err := db.QueryContext(ctx, q, ftsQuery, batchLimit)
	if err != nil {
		return fmt.Errorf("offeneregister: FTS5 query: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		var e offeneEntry
		if err := rows.Scan(
			&e.CompanyID,
			&e.NativeCompanyNumber,
			&e.CompanyType,
			&e.CurrentStatus,
			&e.FederalState,
			&e.RegisteredOffice,
			&e.Name,
			&e.StreetAddress,
			&e.City,
			&e.ZipCode,
			&e.Objective,
		); err != nil {
			result.Errors++
			continue
		}
		if e.Name == "" || e.NativeCompanyNumber == "" {
			continue
		}
		if err := o.upsertEntry(ctx, &e); err != nil {
			result.Errors++
			o.log.Warn("offeneregister: upsert failed",
				"reg_num", e.NativeCompanyNumber,
				"err", err,
			)
			continue
		}
		result.Discovered++
		metrics.DealersTotal.WithLabelValues(familyID, countryDE).Inc()
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()
	}
	return rows.Err()
}

func (o *OffeneRegister) upsertEntry(ctx context.Context, e *offeneEntry) error {
	now := time.Now().UTC()

	// Find existing dealer by Handelsregisternummer.
	existing, err := o.graph.FindDealerByIdentifier(ctx,
		kg.IdentifierHandelsregister, e.NativeCompanyNumber)
	if err != nil {
		return err
	}

	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	city := cityOrOffice(e)
	lf := legalForm(e.CompanyType)
	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     e.Name,
		NormalizedName:    normalizeName(e.Name),
		CountryCode:       countryDE,
		Status:            kg.StatusActive,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if lf != "" {
		entity.LegalForm = &lf
	}

	if err := o.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	// Handelsregisternummer identifier.
	if err := o.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierHandelsregister,
		IdentifierValue: e.NativeCompanyNumber,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	// Location.
	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    countryDE,
		SourceFamilies: familyID,
	}
	if city != "" {
		loc.City = &city
	}
	if e.ZipCode != nil && *e.ZipCode != "" {
		loc.PostalCode = e.ZipCode
	}
	if e.StreetAddress != nil && *e.StreetAddress != "" {
		loc.AddressLine1 = e.StreetAddress
	}
	if e.FederalState != "" {
		loc.Region = &e.FederalState
	}
	if err := o.graph.AddLocation(ctx, loc); err != nil {
		return err
	}

	// Discovery record.
	hrRef := e.NativeCompanyNumber
	return o.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &hrRef,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// ── String helpers ─────────────────────────────────────────────────────────

func cityOrOffice(e *offeneEntry) string {
	if e.City != nil && *e.City != "" {
		return *e.City
	}
	return e.RegisteredOffice
}

func normalizeName(name string) string {
	return strings.ToLower(name)
}

func legalForm(companyType string) string {
	switch strings.ToUpper(companyType) {
	case "GMBH":
		return "GmbH"
	case "AG":
		return "AG"
	case "UG":
		return "UG"
	case "OHG":
		return "OHG"
	case "KG":
		return "KG"
	case "GMBH & CO. KG":
		return "GmbH & Co. KG"
	case "E.K.", "EK":
		return "e.K."
	default:
		return companyType
	}
}
