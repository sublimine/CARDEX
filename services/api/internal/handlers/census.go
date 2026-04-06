package handlers

import (
	"fmt"
	"net/http"
	"strings"
)

// CoverageMatrix handles GET /api/v1/census/coverage-matrix
// Returns the latest snapshot per cell from coverage_matrix, ordered by
// economic_value_eur DESC so the biggest gaps surface first.
//
// Params: country (optional), make (optional), year (optional), limit (default 100)
func (d *Deps) CoverageMatrix(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	country := q.Get("country")
	make_ := q.Get("make")
	year := q.Get("year")
	limit := parseInt(q.Get("limit"), 100)
	if limit > 1000 {
		limit = 1000
	}

	var where []string
	var args []any
	argN := 0

	if country != "" {
		argN++
		where = append(where, fmt.Sprintf("country = $%d", argN))
		args = append(args, country)
	}
	if make_ != "" {
		argN++
		where = append(where, fmt.Sprintf("make = $%d", argN))
		args = append(args, make_)
	}
	if year != "" {
		argN++
		where = append(where, fmt.Sprintf("year = $%d", argN))
		args = append(args, parseInt(year, 0))
	}

	whereClause := "TRUE"
	if len(where) > 0 {
		whereClause = strings.Join(where, " AND ")
	}

	argN++
	query := fmt.Sprintf(`
		SELECT DISTINCT ON (country, make, year, fuel_type)
			country, make, year, fuel_type,
			fleet_count, expected_for_sale, observed_count,
			coverage, economic_value_eur, median_price_eur
		FROM coverage_matrix
		WHERE %s
		ORDER BY country, make, year, fuel_type, computed_at DESC`, whereClause)

	// Wrap in a subquery so we can sort by economic_value_eur and apply limit.
	query = fmt.Sprintf(`SELECT * FROM (%s) sub ORDER BY economic_value_eur DESC LIMIT $%d`, query, argN)
	args = append(args, limit)

	rows, err := d.DB.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "pg_error", err.Error())
		return
	}
	defer rows.Close()

	type cell struct {
		Country          string  `json:"country"`
		Make             string  `json:"make"`
		Year             int     `json:"year"`
		FuelType         string  `json:"fuel_type"`
		FleetCount       int64   `json:"fleet_count"`
		ExpectedForSale  int64   `json:"expected_for_sale"`
		ObservedCount    int64   `json:"observed_count"`
		Coverage         float64 `json:"coverage"`
		EconomicValueEUR float64 `json:"economic_value_eur"`
		MedianPriceEUR   float64 `json:"median_price_eur"`
	}

	var cells []cell
	for rows.Next() {
		var c cell
		if err := rows.Scan(
			&c.Country, &c.Make, &c.Year, &c.FuelType,
			&c.FleetCount, &c.ExpectedForSale, &c.ObservedCount,
			&c.Coverage, &c.EconomicValueEUR, &c.MedianPriceEUR,
		); err != nil {
			continue
		}
		cells = append(cells, c)
	}
	if cells == nil {
		cells = []cell{}
	}
	writeJSON(w, http.StatusOK, cells)
}

// CoverageGaps handles GET /api/v1/census/gaps
// Returns top N gaps where coverage < 1.0 for a given country,
// ordered by economic_value_eur DESC.
//
// Params: country (required), limit (default 20)
func (d *Deps) CoverageGaps(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	country := q.Get("country")
	if country == "" {
		writeError(w, http.StatusBadRequest, "missing_param", "country is required")
		return
	}
	limit := parseInt(q.Get("limit"), 20)
	if limit > 500 {
		limit = 500
	}

	query := `
		SELECT make, year, fuel_type,
			fleet_count, expected_for_sale, observed_count,
			coverage AS coverage_pct,
			(expected_for_sale - observed_count) AS gap_count,
			economic_value_eur
		FROM (
			SELECT DISTINCT ON (country, make, year, fuel_type)
				make, year, fuel_type,
				fleet_count, expected_for_sale, observed_count,
				coverage, economic_value_eur
			FROM coverage_matrix
			WHERE country = $1
			ORDER BY country, make, year, fuel_type, computed_at DESC
		) latest
		WHERE coverage < 1.0
		ORDER BY economic_value_eur DESC
		LIMIT $2`

	rows, err := d.DB.Query(r.Context(), query, country, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "pg_error", err.Error())
		return
	}
	defer rows.Close()

	type gap struct {
		Make             string  `json:"make"`
		Year             int     `json:"year"`
		FuelType         string  `json:"fuel_type"`
		FleetCount       int64   `json:"fleet_count"`
		Expected         int64   `json:"expected"`
		Observed         int64   `json:"observed"`
		CoveragePct      float64 `json:"coverage_pct"`
		GapCount         int64   `json:"gap_count"`
		EconomicValueEUR float64 `json:"economic_value_eur"`
	}

	var gaps []gap
	for rows.Next() {
		var g gap
		if err := rows.Scan(
			&g.Make, &g.Year, &g.FuelType,
			&g.FleetCount, &g.Expected, &g.Observed,
			&g.CoveragePct, &g.GapCount, &g.EconomicValueEUR,
		); err != nil {
			continue
		}
		gaps = append(gaps, g)
	}
	if gaps == nil {
		gaps = []gap{}
	}
	writeJSON(w, http.StatusOK, gaps)
}

// PopulationEstimate handles GET /api/v1/census/population-estimate
// Aggregates fleet_census by country and optionally enriches with a
// Lincoln-Petersen capture-recapture estimate from source_overlap_matrix.
//
// Params: country (required)
func (d *Deps) PopulationEstimate(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	country := q.Get("country")
	if country == "" {
		writeError(w, http.StatusBadRequest, "missing_param", "country is required")
		return
	}

	type result struct {
		Country                  string   `json:"country"`
		TotalFleet               int64    `json:"total_fleet"`
		ExpectedForSale          int64    `json:"expected_for_sale"`
		Observed                 int64    `json:"observed"`
		CoveragePct              float64  `json:"coverage_pct"`
		LincolnPetersenEstimate  *float64 `json:"lincoln_petersen_estimate"`
		ConfidenceInterval       *float64 `json:"confidence_interval"`
	}

	var res result
	res.Country = country

	// Aggregate from coverage_matrix (latest snapshot per cell).
	err := d.DB.QueryRow(r.Context(), `
		SELECT
			COALESCE(SUM(fleet_count), 0),
			COALESCE(SUM(expected_for_sale), 0),
			COALESCE(SUM(observed_count), 0)
		FROM (
			SELECT DISTINCT ON (country, make, year, fuel_type)
				fleet_count, expected_for_sale, observed_count
			FROM coverage_matrix
			WHERE country = $1
			ORDER BY country, make, year, fuel_type, computed_at DESC
		) latest`, country,
	).Scan(&res.TotalFleet, &res.ExpectedForSale, &res.Observed)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "pg_error", err.Error())
		return
	}

	if res.ExpectedForSale > 0 {
		pct := float64(res.Observed) / float64(res.ExpectedForSale)
		res.CoveragePct = pct
	}

	// Lincoln-Petersen capture-recapture from source_overlap_matrix.
	// N_hat = (n1 * n2) / m2  where n1, n2 are source counts and m2 is overlap.
	var n1, n2, m2 float64
	lpErr := d.DB.QueryRow(r.Context(), `
		SELECT only_a_count, only_b_count, overlap_count
		FROM source_overlap_matrix
		WHERE country = $1
		ORDER BY computed_at DESC
		LIMIT 1`, country,
	).Scan(&n1, &n2, &m2)
	if lpErr == nil && m2 > 0 {
		estimate := (n1 * n2) / m2
		// Chapman correction: N_hat = ((n1+1)*(n2+1))/(m2+1) - 1
		chapmanEst := ((n1 + 1) * (n2 + 1) / (m2 + 1)) - 1
		// SE approximation: sqrt((n1+1)*(n2+1)*(n1-m2)*(n2-m2) / ((m2+1)^2*(m2+2)))
		variance := ((n1 + 1) * (n2 + 1) * (n1 - m2) * (n2 - m2)) /
			((m2 + 1) * (m2 + 1) * (m2 + 2))
		_ = estimate // raw LP, we use Chapman-corrected
		ci95 := 1.96 * sqrt(variance)
		res.LincolnPetersenEstimate = &chapmanEst
		res.ConfidenceInterval = &ci95
	}

	writeJSON(w, http.StatusOK, res)
}

// CoverageHeatmap handles GET /api/v1/census/coverage-heatmap
// Joins coverage_matrix with vehicles H3 data for deck.gl visualization.
//
// Params: country (optional), make (optional)
func (d *Deps) CoverageHeatmap(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	country := q.Get("country")
	make_ := q.Get("make")

	var where []string
	var args []any
	argN := 0

	where = append(where, "v.lifecycle_status = 'MARKET_READY'")
	where = append(where, "v.listing_status = 'ACTIVE'")
	where = append(where, "v.h3_index_res4 IS NOT NULL")

	if country != "" {
		argN++
		where = append(where, fmt.Sprintf("v.source_country = $%d", argN))
		args = append(args, country)
	}
	if make_ != "" {
		argN++
		where = append(where, fmt.Sprintf("v.make = $%d", argN))
		args = append(args, make_)
	}

	query := fmt.Sprintf(`
		SELECT
			v.h3_index_res4 AS h3_res4,
			COUNT(*) AS listing_count,
			CASE WHEN cm.expected_for_sale > 0
				THEN LEAST(COUNT(*)::float / cm.expected_for_sale, 1.0)
				ELSE NULL
			END AS coverage_pct,
			AVG(v.gross_physical_cost_eur) AS avg_price_eur
		FROM vehicles v
		LEFT JOIN LATERAL (
			SELECT SUM(expected_for_sale) AS expected_for_sale
			FROM (
				SELECT DISTINCT ON (country, make, year, fuel_type)
					expected_for_sale
				FROM coverage_matrix
				WHERE country = v.source_country AND make = v.make
				ORDER BY country, make, year, fuel_type, computed_at DESC
			) sub
		) cm ON TRUE
		WHERE %s
		GROUP BY v.h3_index_res4, cm.expected_for_sale
		ORDER BY listing_count DESC
		LIMIT 50000`, strings.Join(where, " AND "))

	rows, err := d.DB.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "pg_error", err.Error())
		return
	}
	defer rows.Close()

	type hex struct {
		H3Res4       string   `json:"h3_res4"`
		ListingCount int64    `json:"listing_count"`
		CoveragePct  *float64 `json:"coverage_pct"`
		AvgPriceEUR  float64  `json:"avg_price_eur"`
	}

	var hexes []hex
	for rows.Next() {
		var h hex
		if err := rows.Scan(&h.H3Res4, &h.ListingCount, &h.CoveragePct, &h.AvgPriceEUR); err != nil {
			continue
		}
		hexes = append(hexes, h)
	}
	if hexes == nil {
		hexes = []hex{}
	}
	writeJSON(w, http.StatusOK, hexes)
}

// sqrt is a local helper to avoid importing math for a single call.
func sqrt(x float64) float64 {
	if x <= 0 {
		return 0
	}
	z := x
	for i := 0; i < 50; i++ {
		z = (z + x/z) / 2
	}
	return z
}
