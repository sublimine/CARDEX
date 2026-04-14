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

// KBA ingests vehicle registration statistics from the German Federal Motor Transport Authority.
// Data source: KBA Fahrzeugbestand (Vehicle Fleet) published via Destatis GENESIS.
//
// The KBA publishes monthly fleet statistics broken down by make, fuel type, and registration year.
// This is THE authoritative source for the German vehicle fleet — the largest market in the EU.
//
// Primary endpoint: Destatis GENESIS REST API (table 46251-0002)
// Fallback: KBA direct CSV downloads from flensburg-statistik.de
// Cost: 0€ (public data, Datenlizenz Deutschland – Zero)
type KBA struct {
	httpClient *http.Client
}

func NewKBA() *KBA {
	return &KBA{
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

func (k *KBA) ID() string      { return "KBA" }
func (k *KBA) Country() string { return "DE" }

// Fetch retrieves the latest KBA fleet statistics.
// The KBA publishes data via multiple channels. We try in order:
// 1. Destatis GENESIS REST API (structured, paginated)
// 2. KBA direct CSV (simpler format, monthly snapshots)
func (k *KBA) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("kba: starting fetch")

	// Try KBA direct CSV first (more reliable, simpler parsing)
	records, err := k.fetchKBADirect(ctx)
	if err != nil {
		slog.Warn("kba: direct CSV failed, trying GENESIS", "error", err)
		records, err = k.fetchGenesis(ctx)
		if err != nil {
			return nil, fmt.Errorf("kba: all sources failed: %w", err)
		}
	}

	slog.Info("kba: fetch complete", "records", len(records))
	return records, nil
}

// fetchKBADirect downloads the KBA Fahrzeugbestand CSV from their open data portal.
// URL pattern: https://www.kba.de/SharedDocs/Downloads/DE/Statistik/Fahrzeuge/FZ/fz27/fz27_<year>.csv
// The CSV has columns: make, fuel_type, count (aggregated by year ranges)
func (k *KBA) fetchKBADirect(ctx context.Context) ([]FleetRecord, error) {
	// KBA publishes fleet statistics as FZ1 (total by make) and FZ27 (by fuel type).
	// We use the structured summary endpoint.
	// Fallback: use the GENESIS table which has finer granularity.

	// For now, use the GENESIS API which provides make × fuel × year breakdown.
	return nil, fmt.Errorf("kba: direct CSV not yet implemented, use GENESIS")
}

// fetchGenesis queries the Destatis GENESIS REST API for table 46251-0002.
// This table provides: Bestand an Kraftfahrzeugen nach Marken und Kraftstoffarten.
// API docs: https://www-genesis.destatis.de/genesis/online?Menu=Webservice
//
// The API is free, no key required for flat tables (CSV format).
func (k *KBA) fetchGenesis(ctx context.Context) ([]FleetRecord, error) {
	// GENESIS provides a flat-file download endpoint.
	// Table 46251-0002: Personenkraftwagen nach Marken, Kraftstoffarten
	// We request CSV format with all years available.
	url := "https://www-genesis.destatis.de/genesisWS/rest/2020/data/tablefile" +
		"?username=&password=" +
		"&name=46251-0002" +
		"&area=all" +
		"&compress=false" +
		"&format=ffcsv" +
		"&language=en"

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("kba: genesis request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; census)")

	resp, err := k.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("kba: genesis fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("kba: genesis HTTP %d", resp.StatusCode)
	}

	return k.parseGenesisCSV(resp.Body)
}

func (k *KBA) parseGenesisCSV(r io.Reader) ([]FleetRecord, error) {
	reader := csv.NewReader(r)
	reader.Comma = ';'
	reader.LazyQuotes = true

	var records []FleetRecord
	header := true

	for {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			// Skip malformed rows (GENESIS has metadata rows)
			continue
		}

		// Skip header and metadata rows
		if header {
			if len(row) > 0 && (strings.Contains(row[0], "Zeit") || strings.Contains(row[0], "time")) {
				header = false
			}
			continue
		}

		// Expected GENESIS CSV columns (simplified):
		// [0]=year/date, [1]=make_code, [2]=make_name, [3]=fuel_type, [4]=count
		if len(row) < 5 {
			continue
		}

		yearStr := strings.TrimSpace(row[0])
		year, err := strconv.Atoi(yearStr[:4]) // "2024" or "2024-01-01"
		if err != nil {
			continue
		}

		make_ := NormalizeMake(strings.TrimSpace(row[2]))
		fuel := NormalizeFuel(strings.TrimSpace(row[3]))

		countStr := strings.TrimSpace(row[4])
		countStr = strings.ReplaceAll(countStr, ".", "")  // German thousands separator
		countStr = strings.ReplaceAll(countStr, ",", "")
		countStr = strings.ReplaceAll(countStr, " ", "")
		count, err := strconv.ParseInt(countStr, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "DE",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC),
			Source:      "KBA",
			RawCategory: strings.TrimSpace(row[3]),
		})
	}

	if len(records) == 0 {
		return nil, fmt.Errorf("kba: parsed 0 records from GENESIS CSV")
	}

	return records, nil
}
