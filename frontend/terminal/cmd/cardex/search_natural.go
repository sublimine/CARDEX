package main

// search_natural.go — cardex search-natural subcommand.
//
// Sends a natural-language query to the RAG search service (innovation/rag_search)
// and renders the results in the same ANSI table layout used by `cardex search`.
//
// Fallback: if the RAG server is unavailable, falls back to SQL keyword search
// so the command always returns something useful.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// ── Config ────────────────────────────────────────────────────────────────────

func ragBaseURL() string {
	if u := os.Getenv("CARDEX_RAG_URL"); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://localhost:8502"
}

// ── Request / response types ──────────────────────────────────────────────────

type ragFilterParams struct {
	Country  string  `json:"country,omitempty"`
	PriceMin float64 `json:"price_min,omitempty"`
	PriceMax float64 `json:"price_max,omitempty"`
	KmMax    int     `json:"km_max,omitempty"`
	YearMin  int     `json:"year_min,omitempty"`
	YearMax  int     `json:"year_max,omitempty"`
	FuelType string  `json:"fuel_type,omitempty"`
}

type ragSearchRequest struct {
	Query   string          `json:"query"`
	Filters ragFilterParams `json:"filters"`
	TopK    int             `json:"top_k"`
}

type ragListing struct {
	VehicleID  string  `json:"vehicle_id"`
	Make       string  `json:"make"`
	Model      string  `json:"model"`
	Year       int     `json:"year"`
	MileageKm  int     `json:"mileage_km"`
	PriceEur   float64 `json:"price_eur"`
	Country    string  `json:"country"`
	FuelType   string  `json:"fuel_type"`
	Score      float64 `json:"score"`
	SourceURL  string  `json:"source_url"`
}

type ragSearchResponse struct {
	Results  []ragListing `json:"results"`
	Total    int          `json:"total"`
	QueryMs  float64      `json:"query_ms"`
	Reranked bool         `json:"reranked"`
}

// ── Flags (natural-search-specific) ──────────────────────────────────────────

var (
	flagNatCountry  string
	flagNatPriceMax int
	flagNatPriceMin int
	flagNatKmMax    int
	flagNatYearMin  int
	flagNatYearMax  int
	flagNatFuel     string
	flagNatTopK     int
	flagNatRerank   bool
)

// ── Command ───────────────────────────────────────────────────────────────────

func newSearchNaturalCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "search-natural <query>",
		Short: "Natural-language vehicle search via RAG",
		Long: `Search the CARDEX vehicle index using natural language.

The query is embedded by nomic-embed-text and matched against the FAISS index.
Hard filters (country, price, km) are applied after retrieval.

If the RAG server (CARDEX_RAG_URL / localhost:8502) is unavailable, the
command falls back to a keyword-based SQL search against the local database.`,
		Example: `  cardex search-natural "BMW Serie 3 diesel menos de 100000 km en Alemania"
  cardex search-natural "voiture electrique Paris moins 25000 euros" --country FR
  cardex search-natural "Toyota hybrid low mileage" --price-max 20000 --km-max 60000`,
		Args: cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			query := strings.Join(args, " ")
			return runSearchNatural(query)
		},
	}
	cmd.Flags().StringVar(&flagNatCountry, "country", "", "ISO-3166-1 country code (DE, FR, ES…)")
	cmd.Flags().IntVar(&flagNatPriceMin, "price-min", 0, "minimum price in EUR")
	cmd.Flags().IntVar(&flagNatPriceMax, "price-max", 0, "maximum price in EUR")
	cmd.Flags().IntVar(&flagNatKmMax, "km-max", 0, "maximum odometer reading in km")
	cmd.Flags().IntVar(&flagNatYearMin, "year-min", 0, "minimum model year")
	cmd.Flags().IntVar(&flagNatYearMax, "year-max", 0, "maximum model year")
	cmd.Flags().StringVar(&flagNatFuel, "fuel", "", "fuel type filter (diesel, petrol, hybrid, electric)")
	cmd.Flags().IntVar(&flagNatTopK, "top", 20, "max results to display (1–50)")
	cmd.Flags().BoolVar(&flagNatRerank, "rerank", false, "enable LLM reranking (requires RAG_LLM_RERANK=true on server)")
	return cmd
}

// ── Runner ────────────────────────────────────────────────────────────────────

func runSearchNatural(query string) error {
	results, queryMs, fromFallback, err := fetchRAGResults(query)
	if err != nil {
		// Fallback to SQL keyword search.
		fmt.Println(styleYellow.Render("⚠  RAG server unavailable — falling back to SQL keyword search"))
		return runSQLFallback(query)
	}

	if len(results) == 0 {
		fmt.Println(styleDim.Render("No results found for your query."))
		return nil
	}

	printNaturalResultsTable(query, results, queryMs, fromFallback)
	return nil
}

func fetchRAGResults(query string) ([]ragListing, float64, bool, error) {
	filters := ragFilterParams{
		Country:  flagNatCountry,
		FuelType: flagNatFuel,
	}
	if flagNatPriceMin > 0 {
		filters.PriceMin = float64(flagNatPriceMin)
	}
	if flagNatPriceMax > 0 {
		filters.PriceMax = float64(flagNatPriceMax)
	}
	if flagNatKmMax > 0 {
		filters.KmMax = flagNatKmMax
	}
	if flagNatYearMin > 0 {
		filters.YearMin = flagNatYearMin
	}
	if flagNatYearMax > 0 {
		filters.YearMax = flagNatYearMax
	}
	topK := flagNatTopK
	if topK < 1 {
		topK = 20
	}
	if topK > 50 {
		topK = 50
	}

	reqBody, _ := json.Marshal(ragSearchRequest{
		Query:   query,
		Filters: filters,
		TopK:    topK,
	})

	client := &http.Client{Timeout: 30 * time.Second}
	url := ragBaseURL() + "/search"
	resp, err := client.Post(url, "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return nil, 0, false, fmt.Errorf("RAG server unreachable: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, false, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, 0, false, fmt.Errorf("RAG server returned %d: %s", resp.StatusCode, body)
	}

	var result ragSearchResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, 0, false, fmt.Errorf("parse response: %w", err)
	}
	return result.Results, result.QueryMs, false, nil
}

// ── Output rendering ──────────────────────────────────────────────────────────

func printNaturalResultsTable(query string, results []ragListing, queryMs float64, fallback bool) {
	fmt.Printf("\n%s  %s\n\n",
		styleHeader.Render("NATURAL SEARCH"),
		styleDim.Render(fmt.Sprintf("%q — %.0fms", query, queryMs)),
	)

	hdr := fmt.Sprintf("%-26s %-12s %-18s %5s %8s %8s %6s  %-10s",
		"ID", "COUNTRY/MAKE", "MODEL", "YEAR", "KM", "PRICE€", "SCORE", "FUEL")
	fmt.Println(styleHeader.Render(hdr))
	fmt.Println(strings.Repeat("─", 100))

	for _, r := range results {
		scoreStr := ragScoreStyle(r.Score)
		priceStr := fmt.Sprintf("%8.0f", r.PriceEur)
		urlShort := r.SourceURL
		if len(urlShort) > 35 {
			urlShort = urlShort[:32] + "..."
		}
		line := fmt.Sprintf("%-26s %-12s %-18s %5d %8d %s %s  %-10s  %s",
			r.VehicleID,
			r.Country+"/"+r.Make,
			r.Model,
			r.Year,
			r.MileageKm,
			priceStr,
			scoreStr,
			r.FuelType,
			styleDim.Render(urlShort),
		)
		fmt.Println(line)
	}

	source := "RAG (nomic-embed-text + FAISS)"
	if fallback {
		source = styleYellow.Render("SQL fallback")
	}
	fmt.Printf("\n%s\n",
		styleDim.Render(fmt.Sprintf("%d result(s)  source: %s", len(results), source)),
	)
}

// ragScoreStyle maps cosine similarity (–1..1, typically 0.3–0.95 for matches)
// to a colour-coded percentage string for display.
func ragScoreStyle(score float64) string {
	pct := score * 100
	s := fmt.Sprintf("%5.1f%%", pct)
	switch {
	case score >= 0.75:
		return styleGreen.Render(s)
	case score >= 0.55:
		return styleYellow.Render(s)
	default:
		return styleRed.Render(s)
	}
}

// ── SQL fallback ──────────────────────────────────────────────────────────────

// runSQLFallback performs a simple keyword search when the RAG server is down.
// It tokenises the query and does LIKE matches on make/model.
func runSQLFallback(query string) error {
	db, err := openDB(flagDBPath)
	if err != nil {
		return err
	}
	defer db.Close()

	// Extract potential make/model tokens (words ≥ 3 chars, skip stop-words).
	stopWords := map[string]bool{
		"busco": true, "quiero": true, "menos": true, "por": true, "debajo": true,
		"una": true, "uno": true, "con": true, "sin": true, "the": true, "and": true,
		"for": true, "with": true, "low": true, "cheap": true, "good": true,
	}
	tokens := []string{}
	for _, w := range strings.Fields(strings.ToLower(query)) {
		w = strings.Trim(w, ".,!?\"'")
		if len(w) >= 3 && !stopWords[w] {
			tokens = append(tokens, w)
		}
	}

	// Build a query that OR-matches any token against make or model.
	var conds []string
	var args []any
	for _, t := range tokens {
		conds = append(conds, "(UPPER(vr.make_canonical) LIKE UPPER(?) OR UPPER(vr.model_canonical) LIKE UPPER(?))")
		args = append(args, "%"+t+"%", "%"+t+"%")
	}

	where := ""
	if len(conds) > 0 {
		where = "WHERE " + strings.Join(conds, " OR ")
	}

	// Apply explicit filters if provided.
	if flagNatCountry != "" {
		where += " AND UPPER(de.country_code) = UPPER(?)"
		args = append(args, flagNatCountry)
	}
	if flagNatPriceMax > 0 {
		where += fmt.Sprintf(" AND vr.price_gross_eur <= %d", flagNatPriceMax)
	}
	if flagNatKmMax > 0 {
		where += fmt.Sprintf(" AND vr.mileage_km <= %d", flagNatKmMax)
	}

	sql := fmt.Sprintf(`
		SELECT
			vr.vehicle_id,
			COALESCE(vr.make_canonical, ''),
			COALESCE(vr.model_canonical, ''),
			COALESCE(vr.vin, ''),
			COALESCE(de.country_code, ''),
			COALESCE(vr.year, 0),
			COALESCE(vr.mileage_km, 0),
			CAST(COALESCE(vr.price_gross_eur, 0) AS INTEGER),
			COALESCE(vr.confidence_score, 0.0),
			COALESCE(vr.source_url, ''),
			COALESCE(vr.fuel_type, '')
		FROM vehicle_record vr
		LEFT JOIN dealer_entity de ON de.dealer_id = vr.dealer_id
		%s
		ORDER BY vr.indexed_at DESC
		LIMIT 20`, where)

	rows, err := db.Query(sql, args...)
	if err != nil {
		return fmt.Errorf("SQL fallback: %w", err)
	}
	defer rows.Close()

	type sqlRow struct {
		id, make_, model, vin, country, fuel string
		year, mileage, priceNet              int
		score                                float64
		url                                  string
	}

	var results []ragListing
	for rows.Next() {
		var r sqlRow
		if err := rows.Scan(&r.id, &r.make_, &r.model, &r.vin, &r.country,
			&r.year, &r.mileage, &r.priceNet, &r.score, &r.url, &r.fuel); err != nil {
			return err
		}
		results = append(results, ragListing{
			VehicleID: r.id,
			Make:      r.make_,
			Model:     r.model,
			Year:      r.year,
			MileageKm: r.mileage,
			PriceEur:  float64(r.priceNet),
			Country:   r.country,
			FuelType:  r.fuel,
			Score:     r.score,
			SourceURL: r.url,
		})
	}
	if err := rows.Err(); err != nil {
		return err
	}

	if len(results) == 0 {
		fmt.Println(styleDim.Render("No SQL fallback results found."))
		return nil
	}
	printNaturalResultsTable(query, results, 0, true)
	return nil
}
