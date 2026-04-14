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

// DIV ingests vehicle fleet statistics from the Belgian Directorate for Vehicle Registration (DIV),
// published by Statbel (Belgian Federal Statistical Office).
//
// Statbel publishes monthly "Vehicle stock" (voertuigenpark) data broken down by make, fuel type,
// and province. Belgium has ~6M passenger cars across Flanders, Wallonia, and Brussels.
//
// Data source: https://statbel.fgov.be/en/themes/mobility/traffic/vehicle-stock
// The download page provides CSV/Excel files. The open data endpoint provides direct CSV access.
//
// Statbel also publishes via the Belgian open data portal:
//
//	https://data.gov.be/en/dataset/vehicle-stock
//
// CSV format: semicolon-delimited, with Dutch/French/German column names depending on language.
// Typical columns: Jaar;Merk;Brandstoftype;Aantal (Dutch) or Année;Marque;Type_Carburant;Nombre (French)
//
// Cost: 0€ (open data, Creative Commons CC0)
type DIV struct {
	httpClient *http.Client
}

func NewDIV() *DIV {
	return &DIV{
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

func (d *DIV) ID() string      { return "DIV" }
func (d *DIV) Country() string { return "BE" }

// divDatasetURL is the Statbel open data CSV download for vehicle stock by make and fuel type.
// Statbel publishes monthly snapshots. The URL pattern below points to the latest known
// distribution. If it changes, resolve via the Statbel open data catalog or data.gov.be:
//
//	https://statbel.fgov.be/en/open-data/vehicle-stock
//
// The CSV is semicolon-delimited with columns varying by language. We detect columns dynamically.
const divDatasetURL = "https://statbel.fgov.be/sites/default/files/files/opendata/Verkeer/TF_CAR_FLEET.zip"

// divCSVDirectURL is used when the ZIP download is not practical. Statbel sometimes
// provides a direct CSV endpoint via their open data API.
const divCSVDirectURL = "https://statbel.fgov.be/sites/default/files/files/opendata/Verkeer/TF_CAR_FLEET.csv"

// Fetch retrieves the latest Statbel/DIV fleet statistics.
// We attempt the direct CSV endpoint first, then fall back to the ZIP if needed.
func (d *DIV) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("div: starting fetch")

	// Try direct CSV first
	records, err := d.fetchCSV(ctx, divCSVDirectURL)
	if err != nil {
		slog.Warn("div: direct CSV failed", "error", err)
		// Try alternative URL patterns that Statbel has used historically
		altURL := "https://statbel.fgov.be/sites/default/files/files/opendata/Verkeer/car_fleet.csv"
		records, err = d.fetchCSV(ctx, altURL)
		if err != nil {
			return nil, fmt.Errorf("div: all sources failed: %w", err)
		}
	}

	slog.Info("div: fetch complete", "records", len(records))
	return records, nil
}

// fetchCSV downloads and parses a Statbel fleet CSV.
func (d *DIV) fetchCSV(ctx context.Context, csvURL string) ([]FleetRecord, error) {
	slog.Info("div: downloading CSV", "url", csvURL)

	req, err := http.NewRequestWithContext(ctx, "GET", csvURL, nil)
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; census)")
	req.Header.Set("Accept", "text/csv, application/csv, */*")

	resp, err := d.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d from %s", resp.StatusCode, csvURL)
	}

	return d.parseCSV(resp.Body)
}

// parseCSV parses the Statbel vehicle fleet CSV.
// The CSV can use either Dutch or French column names. We detect columns dynamically.
//
// Dutch:  Jaar;Merk;Brandstoftype;Aantal
// French: Année;Marque;Type_Carburant;Nombre
// English: Year;Make;Fuel_Type;Number
//
// Statbel uses semicolons. Thousands separators may be dots or spaces.
func (d *DIV) parseCSV(r io.Reader) ([]FleetRecord, error) {
	reader := csv.NewReader(r)
	reader.Comma = ';'
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	// Read and analyze header
	headerRow, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}

	// If semicolon yields a single field, try comma or tab
	if len(headerRow) == 1 {
		if strings.Contains(headerRow[0], ",") {
			reader.Comma = ','
			headerRow = strings.Split(headerRow[0], ",")
		} else if strings.Contains(headerRow[0], "\t") {
			reader.Comma = '\t'
			headerRow = strings.Split(headerRow[0], "\t")
		}
	}

	colYear, colMake, colFuel, colCount := -1, -1, -1, -1

	for i, col := range headerRow {
		col = strings.TrimSpace(rawToUpper(col))
		// Strip BOM
		col = strings.TrimPrefix(col, "\xef\xbb\xbf")
		col = strings.TrimPrefix(col, "\ufeff")

		switch {
		// Year: Dutch "JAAR", French "ANNÉE/ANNEE", English "YEAR"
		case col == "JAAR" || col == "YEAR" || contains(col, "ANNEE") || contains(col, "ANNÉE"):
			colYear = i
		// Make: Dutch "MERK", French "MARQUE", English "MAKE/BRAND"
		case col == "MERK" || col == "MARQUE" || col == "MAKE" || col == "BRAND":
			colMake = i
		// Fuel: Dutch "BRANDSTOFTYPE/BRANDSTOF", French "TYPE_CARBURANT/CARBURANT", English "FUEL"
		case contains(col, "BRANDSTOF") || contains(col, "CARBURANT") || contains(col, "FUEL") ||
			contains(col, "ENERGIE"):
			colFuel = i
		// Count: Dutch "AANTAL", French "NOMBRE", English "NUMBER/COUNT"
		case col == "AANTAL" || col == "NOMBRE" || col == "NUMBER" || col == "COUNT" ||
			col == "TOTAL" || contains(col, "AANTAL") || contains(col, "NOMBRE"):
			colCount = i
		}
	}

	if colMake < 0 || colCount < 0 {
		return nil, fmt.Errorf("could not identify required columns (make, count) in header: %v", headerRow)
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

		// Parse year
		year := now.Year()
		if colYear >= 0 && colYear < len(row) {
			yearStr := strings.TrimSpace(row[colYear])
			if y, err := strconv.Atoi(yearStr); err == nil && y >= 1970 && y <= now.Year()+1 {
				year = y
			} else {
				continue
			}
		}

		// Parse make — skip aggregation/total rows
		rawMake := strings.TrimSpace(row[colMake])
		if rawMake == "" || rawMake == "TOTAL" || rawMake == "TOTAAL" || rawMake == "ENSEMBLE" {
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

		// Parse count — handle Belgian thousands separators (dot or space)
		countStr := strings.TrimSpace(row[colCount])
		countStr = strings.ReplaceAll(countStr, ".", "")
		countStr = strings.ReplaceAll(countStr, " ", "")
		countStr = strings.ReplaceAll(countStr, "\u00a0", "")
		// Comma as decimal separator — take integer part
		if idx := strings.Index(countStr, ","); idx >= 0 {
			countStr = countStr[:idx]
		}
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "BE",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 12, 31, 0, 0, 0, 0, time.UTC),
			Source:      "DIV",
			RawCategory: rawFuel,
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("parsed 0 records from Statbel CSV")
	}

	return records, nil
}
