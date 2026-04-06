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

// DGT ingests vehicle registration statistics from the Spanish Dirección General de Tráfico.
//
// The DGT publishes the "Parque de Vehículos" (vehicle fleet) dataset via Spain's open data portal.
// This covers the entire Spanish vehicle fleet broken down by make, fuel type, and province.
// Spain is the 4th-largest EU market (~25M passenger cars).
//
// Data source: datos.gob.es — dataset "Parque de vehículos: Turismos por marca y tipo de carburante"
// The DGT publishes annual CSV snapshots. The dataset ID and download URL may change when new
// vintages are published; the pattern below targets the most recent known structure.
//
// Primary endpoint: datos.gob.es distribution download (CSV)
// The CSV uses semicolon separators and ISO-8859-1 encoding (we handle UTF-8 and Latin-1).
//
// Cost: 0€ (public data, Licencia Abierta / Open License)
type DGT struct {
	httpClient *http.Client
}

func NewDGT() *DGT {
	return &DGT{
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

func (d *DGT) ID() string      { return "DGT" }
func (d *DGT) Country() string { return "ES" }

// datasetURL is the DGT parque vehicular CSV download via datos.gob.es.
// The DGT distributes annual fleet snapshots. This URL pattern points to the latest
// "Parque de vehículos: turismos por marca y tipo de carburante" distribution.
// If the URL changes, update this constant or implement the datos.gob.es CKAN API
// to resolve the latest distribution URL dynamically:
//
//	GET https://datos.gob.es/apidata/catalog/dataset/ea0010587-parque-de-vehiculos
//
// The CSV is semicolon-delimited with columns:
//
//	Año;Provincia;Marca;Tipo_Carburante;Total
const dgtDatasetURL = "https://sedeapl.dgt.gob.es/IEST_INTER/parque_turismos_marca_carburante.csv"

// Fetch retrieves the latest DGT fleet statistics from datos.gob.es.
func (d *DGT) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("dgt: starting fetch", "url", dgtDatasetURL)

	req, err := http.NewRequestWithContext(ctx, "GET", dgtDatasetURL, nil)
	if err != nil {
		return nil, fmt.Errorf("dgt: request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexCensus/1.0 (+https://cardex.eu)")
	req.Header.Set("Accept", "text/csv, application/csv, */*")

	resp, err := d.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("dgt: fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("dgt: HTTP %d", resp.StatusCode)
	}

	records, err := d.parseCSV(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("dgt: parse: %w", err)
	}

	slog.Info("dgt: fetch complete", "records", len(records))
	return records, nil
}

// parseCSV parses the DGT fleet CSV.
// Expected columns: Año;Provincia;Marca;Tipo_Carburante;Total
// Some files may include additional metadata rows at the top (comments starting with #).
// Thousands separators may use dots (Spanish convention: 1.234 = 1234).
func (d *DGT) parseCSV(r io.Reader) ([]FleetRecord, error) {
	reader := csv.NewReader(r)
	reader.Comma = ';'
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	var records []FleetRecord
	headerFound := false
	colYear, colMake, colFuel, colCount := -1, -1, -1, -1

	for {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			// Skip malformed rows (metadata, comments, encoding artifacts)
			continue
		}

		// Skip empty rows
		if len(row) == 0 || (len(row) == 1 && strings.TrimSpace(row[0]) == "") {
			continue
		}

		// Skip comment/metadata rows
		if strings.HasPrefix(strings.TrimSpace(row[0]), "#") {
			continue
		}

		// Detect header row
		if !headerFound {
			for i, col := range row {
				col = strings.TrimSpace(rawToUpper(col))
				switch {
				case col == "AÑO" || col == "ANO" || col == "ANIO" || col == "YEAR" || col == "A\xd1O":
					colYear = i
				case col == "MARCA" || col == "MAKE":
					colMake = i
				case contains(col, "CARBURANTE") || contains(col, "COMBUSTIBLE") || col == "FUEL" || col == "TIPO_CARBURANTE":
					colFuel = i
				case col == "TOTAL" || col == "COUNT" || col == "NUMERO" || col == "CANTIDAD":
					colCount = i
				}
			}
			if colYear >= 0 && colMake >= 0 && colCount >= 0 {
				headerFound = true
			}
			continue
		}

		// Ensure row has enough columns
		maxCol := colYear
		if colMake > maxCol {
			maxCol = colMake
		}
		if colFuel > maxCol {
			maxCol = colFuel
		}
		if colCount > maxCol {
			maxCol = colCount
		}
		if len(row) <= maxCol {
			continue
		}

		// Parse year
		yearStr := strings.TrimSpace(row[colYear])
		year, err := strconv.Atoi(yearStr)
		if err != nil || year < 1970 || year > time.Now().Year()+1 {
			continue
		}

		// Parse make
		rawMake := strings.TrimSpace(row[colMake])
		if rawMake == "" {
			continue
		}
		make_ := NormalizeMake(rawMake)

		// Parse fuel type (may not be present in all datasets)
		fuel := "OTHER"
		rawFuel := ""
		if colFuel >= 0 && colFuel < len(row) {
			rawFuel = strings.TrimSpace(row[colFuel])
			fuel = NormalizeFuel(rawFuel)
		}

		// Parse count — handle Spanish thousands separator (dot) and spaces
		countStr := strings.TrimSpace(row[colCount])
		countStr = strings.ReplaceAll(countStr, ".", "")  // 1.234 → 1234
		countStr = strings.ReplaceAll(countStr, ",", "")  // just in case
		countStr = strings.ReplaceAll(countStr, " ", "")
		countStr = strings.ReplaceAll(countStr, "\u00a0", "") // non-breaking space
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "ES",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 12, 31, 0, 0, 0, 0, time.UTC),
			Source:      "DGT",
			RawCategory: rawFuel,
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("dgt: parsed 0 records from CSV")
	}

	return records, nil
}
