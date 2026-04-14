package sources

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// ASTRA ingests vehicle fleet statistics from the Swiss Federal Roads Office (ASTRA) and
// the Federal Statistical Office (BFS).
//
// The BFS publishes "Strassenfahrzeugbestand" (road vehicle fleet) data via the Swiss open
// data portal (opendata.swiss) and the BFS asset management system (DAM).
// Switzerland has ~4.7M passenger cars.
//
// Data sources:
//   - opendata.swiss: search "Motorfahrzeuge Bestand" or "Strassenfahrzeuge"
//   - BFS DAM: https://dam-api.bfs.admin.ch/hub/api/dam/assets (with search params)
//   - data.bfs.admin.ch: direct statistical tables
//
// The BFS publishes annual CSV/XLSX tables with vehicle fleet by make, fuel type, and canton.
// Table reference: px-x-1103020100_111 (Strassenfahrzeugbestand nach Fahrzeuggruppe und Treibstoff)
//
// Cost: 0€ (OPENDATA.swiss, free use)
type ASTRA struct {
	httpClient *http.Client
}

func NewASTRA() *ASTRA {
	return &ASTRA{
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

func (a *ASTRA) ID() string      { return "ASTRA" }
func (a *ASTRA) Country() string { return "CH" }

// astraPxWebURL is the BFS PxWeb/STAT-TAB API endpoint for vehicle fleet data.
// PxWeb provides structured JSON output. Table px-x-1103020100_111 contains
// "Strassenfahrzeugbestand nach Fahrzeuggruppe, Fahrzeugart und Treibstoff".
//
// The PxWeb API returns data in JSON-stat format when queried with proper parameters.
// Documentation: https://www.pxweb.bfs.admin.ch/
const astraPxWebURL = "https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-1103020100_111/px-x-1103020100_111.px"

// astraCSVFallbackURL is a direct CSV download from the BFS open data portal.
// This URL pattern points to the vehicle fleet by make and fuel type dataset on opendata.swiss.
const astraCSVFallbackURL = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/32007767/master"

// Fetch retrieves the latest ASTRA/BFS fleet statistics.
// Strategy:
//  1. Try the BFS PxWeb JSON-stat API (structured, richest data)
//  2. Fall back to direct CSV download from the BFS DAM
func (a *ASTRA) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("astra: starting fetch")

	// Try CSV download first (more straightforward to parse)
	records, err := a.fetchCSV(ctx)
	if err != nil {
		slog.Warn("astra: CSV download failed, trying PxWeb API", "error", err)
		records, err = a.fetchPxWebJSON(ctx)
		if err != nil {
			return nil, fmt.Errorf("astra: all sources failed: %w", err)
		}
	}

	slog.Info("astra: fetch complete", "records", len(records))
	return records, nil
}

// fetchCSV downloads and parses fleet data from the BFS DAM CSV endpoint.
func (a *ASTRA) fetchCSV(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("astra: downloading CSV", "url", astraCSVFallbackURL)

	req, err := http.NewRequestWithContext(ctx, "GET", astraCSVFallbackURL, nil)
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; census)")
	req.Header.Set("Accept", "text/csv, application/csv, */*")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	return a.parseCSV(resp.Body)
}

// parseCSV parses BFS vehicle fleet CSV data.
// BFS CSVs can use semicolon or comma delimiters and may have German, French, or Italian headers.
//
// German:  Jahr;Marke;Treibstoff;Anzahl
// French:  Année;Marque;Carburant;Nombre
// Italian: Anno;Marca;Carburante;Numero
//
// Swiss thousands separators use apostrophes (1'234) or spaces.
func (a *ASTRA) parseCSV(r io.Reader) ([]FleetRecord, error) {
	reader := csv.NewReader(r)
	reader.Comma = ';'
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	// Read header
	headerRow, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}

	// Auto-detect delimiter
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
		col = strings.TrimPrefix(col, "\xef\xbb\xbf")
		col = strings.TrimPrefix(col, "\ufeff")

		switch {
		// Year: German "JAHR", French "ANNÉE/ANNEE", Italian "ANNO"
		case col == "JAHR" || col == "YEAR" || col == "ANNO" || contains(col, "ANNEE") ||
			contains(col, "ANNÉE") || contains(col, "JAHR"):
			colYear = i
		// Make: German "MARKE", French "MARQUE", Italian "MARCA"
		case col == "MARKE" || col == "MARQUE" || col == "MARCA" || col == "MAKE" ||
			col == "BRAND" || contains(col, "MARKE") || contains(col, "FAHRZEUGMARKE"):
			colMake = i
		// Fuel: German "TREIBSTOFF/TREIBSTOFFART", French "CARBURANT", Italian "CARBURANTE"
		case contains(col, "TREIBSTOFF") || contains(col, "CARBURANT") || contains(col, "FUEL") ||
			contains(col, "ANTRIEB") || contains(col, "ENERGIE"):
			colFuel = i
		// Count: German "ANZAHL/BESTAND", French "NOMBRE", Italian "NUMERO"
		case col == "ANZAHL" || col == "BESTAND" || col == "NOMBRE" || col == "NUMERO" ||
			col == "COUNT" || col == "TOTAL" || contains(col, "ANZAHL") || contains(col, "BESTAND"):
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

		// Parse make — skip total/aggregate rows
		rawMake := strings.TrimSpace(row[colMake])
		if rawMake == "" || rawMake == "TOTAL" || rawMake == "INSGESAMT" || rawMake == "ENSEMBLE" ||
			rawMake == "TOTALE" {
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

		// Parse count — handle Swiss apostrophe thousands separator (1'234)
		countStr := strings.TrimSpace(row[colCount])
		countStr = strings.ReplaceAll(countStr, "'", "")  // Swiss: 1'234 → 1234
		countStr = strings.ReplaceAll(countStr, "'", "")  // Typographic apostrophe
		countStr = strings.ReplaceAll(countStr, " ", "")
		countStr = strings.ReplaceAll(countStr, "\u00a0", "")
		countStr = strings.ReplaceAll(countStr, ".", "")
		// Comma as decimal — take integer part
		if idx := strings.Index(countStr, ","); idx >= 0 {
			countStr = countStr[:idx]
		}
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "CH",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 12, 31, 0, 0, 0, 0, time.UTC),
			Source:      "ASTRA",
			RawCategory: rawFuel,
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("parsed 0 records from BFS CSV")
	}

	return records, nil
}

// fetchPxWebJSON queries the BFS PxWeb API for vehicle fleet data in JSON-stat format.
// The PxWeb API requires a POST with a query body specifying which dimensions to select.
func (a *ASTRA) fetchPxWebJSON(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("astra: querying PxWeb API", "url", astraPxWebURL)

	// PxWeb query: select all makes, all fuel types, latest year, passenger cars only
	queryBody := `{
		"query": [
			{
				"code": "Fahrzeuggruppe",
				"selection": {
					"filter": "item",
					"values": ["1"]
				}
			}
		],
		"response": {
			"format": "json"
		}
	}`

	req, err := http.NewRequestWithContext(ctx, "POST", astraPxWebURL, strings.NewReader(queryBody))
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; census)")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("PxWeb HTTP %d", resp.StatusCode)
	}

	return a.parsePxWebJSON(resp.Body)
}

// parsePxWebJSON parses the PxWeb JSON response.
// PxWeb returns a JSON structure with dimension metadata and a flat value array.
// The format is:
//
//	{
//	  "columns": [{"code":"Marke","text":"Marke",...}, {"code":"Treibstoff",...}, {"code":"Jahr",...}],
//	  "data": [{"key":["BMW","Benzin","2024"], "values":["12345"]}, ...]
//	}
func (a *ASTRA) parsePxWebJSON(r io.Reader) ([]FleetRecord, error) {
	body, err := io.ReadAll(io.LimitReader(r, 50*1024*1024)) // 50MB limit
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	var pxResp pxWebResponse
	if err := json.Unmarshal(body, &pxResp); err != nil {
		return nil, fmt.Errorf("decode JSON: %w", err)
	}

	// Map column codes to indices
	colMake, colFuel, colYear := -1, -1, -1
	for i, col := range pxResp.Columns {
		code := rawToUpper(col.Code)
		switch {
		case contains(code, "MARKE") || contains(code, "MARQUE") || contains(code, "BRAND"):
			colMake = i
		case contains(code, "TREIBSTOFF") || contains(code, "CARBURANT") || contains(code, "FUEL"):
			colFuel = i
		case contains(code, "JAHR") || contains(code, "ANNEE") || contains(code, "YEAR") || contains(code, "ZEIT"):
			colYear = i
		}
	}

	if colMake < 0 {
		return nil, fmt.Errorf("could not identify make column in PxWeb response")
	}

	var records []FleetRecord
	now := time.Now()

	for _, d := range pxResp.Data {
		if len(d.Values) == 0 {
			continue
		}

		// Parse count
		countStr := strings.TrimSpace(d.Values[0])
		countStr = strings.ReplaceAll(countStr, "'", "")
		countStr = strings.ReplaceAll(countStr, " ", "")
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		// Parse make
		if colMake >= len(d.Key) {
			continue
		}
		rawMake := strings.TrimSpace(d.Key[colMake])
		if rawMake == "" || rawMake == "Total" || rawMake == "Insgesamt" {
			continue
		}
		make_ := NormalizeMake(rawMake)

		// Parse fuel type
		fuel := "OTHER"
		rawFuel := ""
		if colFuel >= 0 && colFuel < len(d.Key) {
			rawFuel = strings.TrimSpace(d.Key[colFuel])
			fuel = NormalizeFuel(rawFuel)
		}

		// Parse year
		year := now.Year()
		if colYear >= 0 && colYear < len(d.Key) {
			if y, err := strconv.Atoi(strings.TrimSpace(d.Key[colYear])); err == nil {
				year = y
			}
		}

		records = append(records, FleetRecord{
			Country:     "CH",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 12, 31, 0, 0, 0, 0, time.UTC),
			Source:      "ASTRA",
			RawCategory: rawFuel,
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("parsed 0 records from PxWeb JSON")
	}

	return records, nil
}

// pxWebResponse represents the PxWeb/STAT-TAB JSON output format.
type pxWebResponse struct {
	Columns []pxWebColumn `json:"columns"`
	Data    []pxWebData   `json:"data"`
}

type pxWebColumn struct {
	Code string `json:"code"`
	Text string `json:"text"`
}

type pxWebData struct {
	Key    []string `json:"key"`
	Values []string `json:"values"`
}
