package sources

import (
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// SDES ingests vehicle fleet statistics from the French Ministère de la Transition Écologique,
// published by the Service des Données et Études Statistiques (SDES).
//
// The dataset "Parc automobile roulant" (rolling vehicle fleet) is published on data.gouv.fr.
// France is the 2nd-largest EU market (~39M passenger cars).
//
// Data source: data.gouv.fr — dataset "parc-automobile-roulant"
// Published by: Commissariat général au développement durable / SDES
// The SDES publishes annual CSV files with the fleet broken down by:
//   - Marque (make), Energie (fuel type), Année du modèle (model year), Nombre (count)
//
// The dataset ID on data.gouv.fr is stable; the distribution (CSV file) URL may update
// annually. To resolve dynamically, query the data.gouv.fr API:
//
//	GET https://www.data.gouv.fr/api/1/datasets/parc-automobile-roulant/
//
// Cost: 0€ (Licence Ouverte / Open Licence Etalab)
type SDES struct {
	httpClient *http.Client
}

func NewSDES() *SDES {
	return &SDES{
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

func (s *SDES) ID() string      { return "SDES" }
func (s *SDES) Country() string { return "FR" }

// sdesDatasetAPIURL is the data.gouv.fr API endpoint that lists distributions (CSV files)
// for the parc automobile roulant dataset. We query this first to find the latest CSV URL.
const sdesDatasetAPIURL = "https://www.data.gouv.fr/api/1/datasets/parc-automobile-roulant/"

// sdesFallbackCSVURL is a direct download URL for the latest known CSV distribution.
// This is used if the API resolution fails. The URL may need updating when SDES
// publishes a new vintage.
const sdesFallbackCSVURL = "https://www.data.gouv.fr/fr/datasets/r/parc-automobile-roulant.csv"

// Fetch retrieves the latest SDES fleet statistics.
// Strategy: try to resolve the latest CSV URL via the data.gouv.fr API, fall back to
// a known direct URL if the API is unavailable.
func (s *SDES) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("sdes: starting fetch")

	// Try direct CSV download first (most reliable in practice)
	csvURL := sdesFallbackCSVURL

	// Attempt to resolve latest CSV from the API
	resolvedURL, err := s.resolveLatestCSV(ctx)
	if err != nil {
		slog.Warn("sdes: API resolution failed, using fallback URL", "error", err)
	} else if resolvedURL != "" {
		csvURL = resolvedURL
	}

	records, err := s.fetchAndParseCSV(ctx, csvURL)
	if err != nil {
		return nil, fmt.Errorf("sdes: %w", err)
	}

	slog.Info("sdes: fetch complete", "records", len(records))
	return records, nil
}

// resolveLatestCSV queries the data.gouv.fr API to find the latest CSV resource
// in the parc-automobile-roulant dataset.
func (s *SDES) resolveLatestCSV(ctx context.Context) (string, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", sdesDatasetAPIURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "CardexCensus/1.0 (+https://cardex.eu)")
	req.Header.Set("Accept", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("API HTTP %d", resp.StatusCode)
	}

	// We only need the resources[].url field where format == "csv"
	// Parse minimally to avoid importing encoding/json for a large response
	body, err := io.ReadAll(io.LimitReader(resp.Body, 2*1024*1024)) // 2MB limit
	if err != nil {
		return "", err
	}

	// Simple heuristic: find the last CSV URL in the response.
	// The data.gouv.fr API returns resources ordered by recency.
	bodyStr := string(body)
	csvURLs := extractCSVURLs(bodyStr)
	if len(csvURLs) > 0 {
		return csvURLs[0], nil
	}

	return "", fmt.Errorf("no CSV resource found in API response")
}

// extractCSVURLs finds URLs ending in .csv from a JSON response body.
func extractCSVURLs(body string) []string {
	var urls []string
	// Look for "url":"..." patterns where the URL contains .csv
	searchFrom := 0
	for {
		idx := indexAt(body, `"url":"`, searchFrom)
		if idx < 0 {
			break
		}
		start := idx + len(`"url":"`)
		end := indexAt(body, `"`, start)
		if end < 0 {
			break
		}
		u := body[start:end]
		if strings.HasSuffix(strings.ToLower(u), ".csv") || contains(rawToUpper(u), "CSV") {
			urls = append(urls, u)
		}
		searchFrom = end + 1
	}
	return urls
}

func indexAt(s, sub string, from int) int {
	if from >= len(s) {
		return -1
	}
	idx := strings.Index(s[from:], sub)
	if idx < 0 {
		return -1
	}
	return from + idx
}

// fetchAndParseCSV downloads and parses the SDES fleet CSV.
func (s *SDES) fetchAndParseCSV(ctx context.Context, csvURL string) ([]FleetRecord, error) {
	slog.Info("sdes: downloading CSV", "url", csvURL)

	req, err := http.NewRequestWithContext(ctx, "GET", csvURL, nil)
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexCensus/1.0 (+https://cardex.eu)")
	req.Header.Set("Accept", "text/csv, application/csv, */*")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d from %s", resp.StatusCode, csvURL)
	}

	return s.parseCSV(resp.Body)
}

// parseCSV parses the SDES parc automobile CSV.
// Expected columns vary by vintage but typically include:
//
//	Annee;Marque;Energie;Nombre  (or similar French column names)
//
// The CSV uses semicolons (French convention) and may have metadata header rows.
// Thousands may use spaces (French convention: 1 234 = 1234).
func (s *SDES) parseCSV(r io.Reader) ([]FleetRecord, error) {
	reader := csv.NewReader(r)
	reader.Comma = ';'
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	// Try comma as well if semicolon yields single-column rows
	firstRow, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}

	// If first row has only 1 field, the delimiter is probably comma
	if len(firstRow) == 1 && strings.Contains(firstRow[0], ",") {
		// Re-read is not possible on a stream, so we parse the rest with comma.
		// This is a fallback for datasets using comma instead of semicolon.
		reader.Comma = ','
		// Re-split the first row
		firstRow = strings.Split(firstRow[0], ",")
	}

	// Map column names to indices
	colYear, colMake, colFuel, colCount := -1, -1, -1, -1
	for i, col := range firstRow {
		col = strings.TrimSpace(rawToUpper(col))
		// Remove BOM if present
		col = strings.TrimPrefix(col, "\xef\xbb\xbf")
		col = strings.TrimPrefix(col, "\ufeff")
		switch {
		case col == "ANNEE" || col == "ANNÉE" || col == "ANNEE_MODELE" || col == "YEAR" ||
			contains(col, "ANNEE") || contains(col, "ANNÉE"):
			colYear = i
		case col == "MARQUE" || col == "MAKE" || contains(col, "MARQUE"):
			colMake = i
		case col == "ENERGIE" || col == "ÉNERGIE" || col == "FUEL" || contains(col, "ENERGIE") ||
			contains(col, "CARBURANT"):
			colFuel = i
		case col == "NOMBRE" || col == "NB" || col == "COUNT" || col == "PARC" ||
			contains(col, "NOMBRE") || contains(col, "PARC"):
			colCount = i
		}
	}

	if colMake < 0 || colCount < 0 {
		return nil, fmt.Errorf("could not identify required columns (make, count) in header: %v", firstRow)
	}

	var records []FleetRecord
	now := time.Now()

	for {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		// Determine max needed column
		maxCol := colCount
		if colMake > maxCol {
			maxCol = colMake
		}
		if colYear > maxCol {
			maxCol = colYear
		}
		if colFuel > maxCol {
			maxCol = colFuel
		}
		if len(row) <= maxCol {
			continue
		}

		// Parse year (default to current year if column not present)
		year := now.Year()
		if colYear >= 0 && colYear < len(row) {
			yearStr := strings.TrimSpace(row[colYear])
			if y, err := strconv.Atoi(yearStr); err == nil && y >= 1970 && y <= now.Year()+1 {
				year = y
			} else {
				continue
			}
		}

		// Parse make
		rawMake := strings.TrimSpace(row[colMake])
		if rawMake == "" || rawMake == "TOTAL" || rawMake == "ENSEMBLE" {
			continue
		}
		make_ := NormalizeMake(rawMake)

		// Parse fuel type
		fuel := "OTHER"
		rawFuel := ""
		if colFuel >= 0 && colFuel < len(row) {
			rawFuel = strings.TrimSpace(row[colFuel])
			fuel = NormalizeFuel(rawFuel)
		}

		// Parse count — handle French thousands separator (space) and comma decimal
		countStr := strings.TrimSpace(row[colCount])
		countStr = strings.ReplaceAll(countStr, " ", "")
		countStr = strings.ReplaceAll(countStr, "\u00a0", "") // non-breaking space
		countStr = strings.ReplaceAll(countStr, ".", "")
		// If there's a comma, it might be a decimal separator; take integer part
		if idx := strings.Index(countStr, ","); idx >= 0 {
			countStr = countStr[:idx]
		}
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "FR",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 12, 31, 0, 0, 0, 0, time.UTC),
			Source:      "SDES",
			RawCategory: rawFuel,
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("parsed 0 records from SDES CSV")
	}

	return records, nil
}
