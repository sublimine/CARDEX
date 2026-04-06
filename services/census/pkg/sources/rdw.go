package sources

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
)

// RDW ingests vehicle registration data from the Dutch Road Transport Authority (Rijksdienst voor het Wegverkeer).
//
// The RDW publishes the ENTIRE Dutch vehicle fleet (~15M records) via a Socrata Open Data API (SODA).
// This is the most granular free government vehicle data in the world:
// - VIN-level (kenteken = license plate, linked to VIN)
// - APK (ITV) expiry dates
// - First registration date
// - Make, model, fuel type, CO2, mass, power
// - Insurance status
//
// For the census, we aggregate by make/year/fuel to get fleet counts.
// The VIN-level data is used separately for supply prediction (APK expiry → likely sale).
//
// Endpoint: https://opendata.rdw.nl/resource/m9d7-ebf2.json (SODA API)
// Rate limit: 1000 req/hour unauthenticated, 10K with app token (free registration)
// Cost: 0€
type RDW struct {
	httpClient *http.Client
	appToken   string // Optional Socrata app token for higher rate limits
}

func NewRDW(appToken string) *RDW {
	return &RDW{
		httpClient: &http.Client{Timeout: 120 * time.Second},
		appToken:   appToken,
	}
}

func (r *RDW) ID() string      { return "RDW" }
func (r *RDW) Country() string { return "NL" }

// Fetch retrieves aggregated fleet statistics from RDW.
// Instead of downloading all 15M records, we use SODA's $group aggregation
// to get counts by make, year of first registration, and fuel type.
func (r *RDW) Fetch(ctx context.Context) ([]FleetRecord, error) {
	slog.Info("rdw: starting aggregated fetch")

	var allRecords []FleetRecord
	offset := 0
	limit := 10000

	for {
		records, hasMore, err := r.fetchPage(ctx, offset, limit)
		if err != nil {
			return nil, err
		}
		allRecords = append(allRecords, records...)
		if !hasMore {
			break
		}
		offset += limit

		// Safety: don't fetch more than 100K aggregated rows
		if offset > 100000 {
			slog.Warn("rdw: safety limit reached", "offset", offset)
			break
		}
	}

	slog.Info("rdw: fetch complete", "records", len(allRecords))
	return allRecords, nil
}

// fetchPage retrieves one page of aggregated results using SODA $query.
// The query groups by merk (make), datum_eerste_toelating (first registration date), and brandstof_omschrijving (fuel type),
// then counts records per group.
func (r *RDW) fetchPage(ctx context.Context, offset, limit int) ([]FleetRecord, bool, error) {
	// SODA SoQL aggregation query:
	// SELECT merk, date_extract_y(datum_eerste_toelating_dt) as reg_year, brandstof_omschrijving, count(*) as cnt
	// GROUP BY merk, reg_year, brandstof_omschrijving
	// ORDER BY cnt DESC
	// LIMIT {limit} OFFSET {offset}
	//
	// Dataset: m9d7-ebf2 (Gekentekende voertuigen - all registered vehicles)
	query := fmt.Sprintf(
		`SELECT merk, date_extract_y(datum_eerste_toelating_dt) as reg_year, brandstof_omschrijving, count(*) as cnt `+
			`WHERE voertuigsoort='Personenauto' AND datum_eerste_toelating_dt IS NOT NULL `+
			`GROUP BY merk, reg_year, brandstof_omschrijving `+
			`ORDER BY cnt DESC `+
			`LIMIT %d OFFSET %d`,
		limit, offset,
	)

	params := url.Values{}
	params.Set("$query", query)

	reqURL := "https://opendata.rdw.nl/resource/m9d7-ebf2.json?" + params.Encode()

	req, err := http.NewRequestWithContext(ctx, "GET", reqURL, nil)
	if err != nil {
		return nil, false, fmt.Errorf("rdw: request: %w", err)
	}
	req.Header.Set("User-Agent", "CardexCensus/1.0 (+https://cardex.eu)")
	if r.appToken != "" {
		req.Header.Set("X-App-Token", r.appToken)
	}

	resp, err := r.httpClient.Do(req)
	if err != nil {
		return nil, false, fmt.Errorf("rdw: fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, false, fmt.Errorf("rdw: HTTP %d", resp.StatusCode)
	}

	var rows []rdwAggRow
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return nil, false, fmt.Errorf("rdw: decode: %w", err)
	}

	var records []FleetRecord
	now := time.Now()
	for _, row := range rows {
		make_ := NormalizeMake(strings.TrimSpace(row.Merk))
		fuel := NormalizeFuel(strings.TrimSpace(row.Brandstof))

		year, err := strconv.Atoi(row.RegYear)
		if err != nil || year < 1970 || year > now.Year()+1 {
			continue
		}

		count, err := strconv.ParseInt(row.Count, 10, 64)
		if err != nil || count <= 0 {
			continue
		}

		records = append(records, FleetRecord{
			Country:     "NL",
			Make:        make_,
			Year:        year,
			FuelType:    fuel,
			Count:       count,
			AsOfDate:    now.Truncate(24 * time.Hour),
			Source:      "RDW",
			RawCategory: row.Brandstof,
		})
	}

	hasMore := len(rows) == limit
	return records, hasMore, nil
}

type rdwAggRow struct {
	Merk      string `json:"merk"`
	RegYear   string `json:"reg_year"`
	Brandstof string `json:"brandstof_omschrijving"`
	Count     string `json:"cnt"`
}
