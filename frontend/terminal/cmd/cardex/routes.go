package main

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

// ── Styles (routes-specific) ──────────────────────────────────────────────────

var (
	styleTeal   = lipgloss.NewStyle().Foreground(lipgloss.Color("6"))
	styleOrange = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
)

// ── Routes API types (local copies — no module dependency) ───────────────────

type routesOptimizeReq struct {
	VIN            string `json:"vin,omitempty"`
	Make           string `json:"make"`
	Model          string `json:"model"`
	Year           int    `json:"year"`
	MileageKm      int    `json:"mileage_km"`
	FuelType       string `json:"fuel_type,omitempty"`
	CurrentCountry string `json:"current_country"`
	Channel        string `json:"channel,omitempty"`
}

type routesDispositionRoute struct {
	FromCountry      string  `json:"from_country"`
	ToCountry        string  `json:"to_country"`
	Channel          string  `json:"channel"`
	EstimatedPrice   int64   `json:"estimated_price_cents"`
	VATCost          int64   `json:"vat_cost_cents"`
	TransportCost    int64   `json:"transport_cost_cents"`
	NetProfit        int64   `json:"net_profit_cents"`
	TimeToSellDays   int     `json:"time_to_sell_days"`
	AvailableDealers int     `json:"available_dealers"`
	Confidence       float64 `json:"confidence"`
	Explanation      string  `json:"explanation"`
}

type routesDispositionPlan struct {
	VehicleVIN     string                   `json:"vehicle_vin"`
	Make           string                   `json:"make"`
	Model          string                   `json:"model"`
	Year           int                      `json:"year"`
	MileageKm      int                      `json:"mileage_km"`
	CurrentCountry string                   `json:"current_country"`
	Routes         []routesDispositionRoute `json:"routes"`
	BestRoute      routesDispositionRoute   `json:"best_route"`
	TotalUplift    int64                    `json:"total_uplift_cents"`
	ComputedAt     time.Time                `json:"computed_at"`
}

type routesMarketSpread struct {
	Make             string           `json:"make"`
	Model            string           `json:"model"`
	Year             int              `json:"year"`
	MileageBracket   string           `json:"mileage_bracket"`
	PricesByCountry  map[string]int64 `json:"prices_by_country_cents"`
	SamplesByCountry map[string]int   `json:"samples_by_country"`
	BestCountry      string           `json:"best_country"`
	WorstCountry     string           `json:"worst_country"`
	SpreadAmount     int64            `json:"spread_amount_cents"`
	Confidence       float64          `json:"confidence"`
}

type routesBatchPlan struct {
	TotalVehicles         int            `json:"total_vehicles"`
	TotalEstimatedUplift  int64          `json:"total_estimated_uplift_cents"`
	AvgUpliftPerVehicle   int64          `json:"avg_uplift_per_vehicle_cents"`
	ByDestination         map[string]int `json:"by_destination"`
	CapConstraintApplied  int            `json:"cap_constraint_applied"`
	ComputedAt            time.Time      `json:"computed_at"`
}

// ── Flag vars ─────────────────────────────────────────────────────────────────

var (
	flagRoutesURL     string
	flagRoutesMake    string
	flagRoutesModel   string
	flagRoutesYear    int
	flagRoutesKm      int
	flagRoutesFuel    string
	flagRoutesCountry string
	flagRoutesVIN     string
	flagRoutesChannel string
	flagRoutesInput   string
	flagRoutesOutput  string
)

// ── Command ───────────────────────────────────────────────────────────────────

func newRoutesCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "routes",
		Short: "Fleet disposition intelligence — find the best cross-border route for your vehicles",
	}
	cmd.PersistentFlags().StringVar(&flagRoutesURL, "url", "",
		"Routes API base URL (env: ROUTES_URL, default: http://localhost:8504)")
	cmd.AddCommand(newRoutesOptimizeCmd())
	cmd.AddCommand(newRoutesSpreadCmd())
	cmd.AddCommand(newRoutesBatchCmd())
	return cmd
}

func routesBaseURL() string {
	if flagRoutesURL != "" {
		return flagRoutesURL
	}
	if v := os.Getenv("ROUTES_URL"); v != "" {
		return v
	}
	return "http://localhost:8504"
}

// ── cardex routes optimize ────────────────────────────────────────────────────

func newRoutesOptimizeCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "optimize",
		Short: "Find the best disposition route for a single vehicle",
		Example: `  cardex routes optimize --make BMW --model "320d" --year 2021 --km 45000 --country FR
  cardex routes optimize --vin WBAAAAAAA --make BMW --model 320d --year 2021 --km 45000 --country DE`,
		RunE: runRoutesOptimize,
	}
	cmd.Flags().StringVar(&flagRoutesMake, "make", "", "vehicle make (required)")
	cmd.Flags().StringVar(&flagRoutesModel, "model", "", "vehicle model (required)")
	cmd.Flags().IntVar(&flagRoutesYear, "year", 0, "model year (required)")
	cmd.Flags().IntVar(&flagRoutesKm, "km", 0, "odometer reading in km")
	cmd.Flags().StringVar(&flagRoutesFuel, "fuel", "", "fuel type (optional)")
	cmd.Flags().StringVar(&flagRoutesCountry, "country", "", "current country ISO code (required)")
	cmd.Flags().StringVar(&flagRoutesVIN, "vin", "", "VIN (optional)")
	cmd.Flags().StringVar(&flagRoutesChannel, "channel", "", "preferred channel: dealer_direct|auction|export")
	_ = cmd.MarkFlagRequired("make")
	_ = cmd.MarkFlagRequired("model")
	_ = cmd.MarkFlagRequired("year")
	_ = cmd.MarkFlagRequired("country")
	return cmd
}

func runRoutesOptimize(_ *cobra.Command, _ []string) error {
	req := routesOptimizeReq{
		VIN:            flagRoutesVIN,
		Make:           flagRoutesMake,
		Model:          flagRoutesModel,
		Year:           flagRoutesYear,
		MileageKm:      flagRoutesKm,
		FuelType:       flagRoutesFuel,
		CurrentCountry: strings.ToUpper(flagRoutesCountry),
		Channel:        flagRoutesChannel,
	}
	body, _ := json.Marshal(req)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Post(routesBaseURL()+"/routes/optimize", "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("routes service unreachable (%s): %w\n\nStart with: make routes-serve", routesBaseURL(), err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("no market data for %s %s %d in any country", req.Make, req.Model, req.Year)
	}
	if resp.StatusCode != http.StatusOK {
		var e map[string]string
		_ = json.NewDecoder(resp.Body).Decode(&e)
		return fmt.Errorf("API error %d: %s", resp.StatusCode, e["error"])
	}

	var plan routesDispositionPlan
	if err := json.NewDecoder(resp.Body).Decode(&plan); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	renderDispositionPlan(&plan)
	return nil
}

// ── cardex routes spread ──────────────────────────────────────────────────────

func newRoutesSpreadCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "spread",
		Short: "Show market price spread across all countries for a vehicle cohort",
		Example: `  cardex routes spread --make BMW --model "320d" --year 2021
  cardex routes spread --make Renault --model Clio --year 2019 --km 60000`,
		RunE: runRoutesSpread,
	}
	cmd.Flags().StringVar(&flagRoutesMake, "make", "", "vehicle make (required)")
	cmd.Flags().StringVar(&flagRoutesModel, "model", "", "vehicle model (required)")
	cmd.Flags().IntVar(&flagRoutesYear, "year", 0, "model year (required)")
	cmd.Flags().IntVar(&flagRoutesKm, "km", 0, "mileage (optional, used for bracket)")
	cmd.Flags().StringVar(&flagRoutesFuel, "fuel", "", "fuel type (optional)")
	_ = cmd.MarkFlagRequired("make")
	_ = cmd.MarkFlagRequired("model")
	_ = cmd.MarkFlagRequired("year")
	return cmd
}

func runRoutesSpread(_ *cobra.Command, _ []string) error {
	params := url.Values{}
	params.Set("make", flagRoutesMake)
	params.Set("model", flagRoutesModel)
	params.Set("year", strconv.Itoa(flagRoutesYear))
	if flagRoutesKm > 0 {
		params.Set("km", strconv.Itoa(flagRoutesKm))
	}
	if flagRoutesFuel != "" {
		params.Set("fuel", flagRoutesFuel)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Get(routesBaseURL() + "/routes/spread?" + params.Encode())
	if err != nil {
		return fmt.Errorf("routes service unreachable: %w", err)
	}
	defer resp.Body.Close()

	var spread routesMarketSpread
	if err := json.NewDecoder(resp.Body).Decode(&spread); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	renderMarketSpread(&spread)
	return nil
}

// ── cardex routes batch ───────────────────────────────────────────────────────

func newRoutesBatchCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "batch",
		Short: "Optimize disposition for an entire fleet from a CSV file",
		Example: `  cardex routes batch --input fleet.csv --output plan.json
  # fleet.csv columns: vin,make,model,year,mileage_km,fuel_type,country`,
		RunE: runRoutesBatch,
	}
	cmd.Flags().StringVar(&flagRoutesInput, "input", "", "path to fleet CSV file (required)")
	cmd.Flags().StringVar(&flagRoutesOutput, "output", "", "path to output JSON plan (default: stdout)")
	_ = cmd.MarkFlagRequired("input")
	return cmd
}

type vehicleInputJSON struct {
	VIN            string `json:"vin,omitempty"`
	Make           string `json:"make"`
	Model          string `json:"model"`
	Year           int    `json:"year"`
	MileageKm      int    `json:"mileage_km"`
	FuelType       string `json:"fuel_type,omitempty"`
	CurrentCountry string `json:"current_country"`
}

func runRoutesBatch(_ *cobra.Command, _ []string) error {
	vehicles, err := loadFleetCSV(flagRoutesInput)
	if err != nil {
		return fmt.Errorf("load fleet: %w", err)
	}
	if len(vehicles) == 0 {
		return fmt.Errorf("fleet CSV is empty")
	}

	body, _ := json.Marshal(vehicles)
	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Post(routesBaseURL()+"/routes/batch", "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("routes service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var e map[string]string
		_ = json.NewDecoder(resp.Body).Decode(&e)
		return fmt.Errorf("API error %d: %s", resp.StatusCode, e["error"])
	}

	respBody, _ := io.ReadAll(resp.Body)

	if flagRoutesOutput == "" {
		// Pretty-print to stdout.
		var plan routesBatchPlan
		if err := json.Unmarshal(respBody, &plan); err != nil {
			return err
		}
		renderBatchSummary(&plan, len(vehicles))
		return nil
	}

	// Write raw JSON to output file.
	if err := os.WriteFile(flagRoutesOutput, respBody, 0o644); err != nil {
		return fmt.Errorf("write output: %w", err)
	}
	fmt.Printf("Fleet plan written to %s (%d vehicles)\n", flagRoutesOutput, len(vehicles))
	return nil
}

// loadFleetCSV reads a CSV file and returns a slice of vehicle inputs.
// Expected columns (header required): vin,make,model,year,mileage_km,fuel_type,country
func loadFleetCSV(path string) ([]vehicleInputJSON, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.TrimLeadingSpace = true
	header, err := r.Read()
	if err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}
	colIdx := make(map[string]int)
	for i, h := range header {
		colIdx[strings.ToLower(strings.TrimSpace(h))] = i
	}

	col := func(row []string, name string) string {
		if i, ok := colIdx[name]; ok && i < len(row) {
			return strings.TrimSpace(row[i])
		}
		return ""
	}

	var vehicles []vehicleInputJSON
	for {
		row, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		year, _ := strconv.Atoi(col(row, "year"))
		km, _ := strconv.Atoi(col(row, "mileage_km"))
		vehicles = append(vehicles, vehicleInputJSON{
			VIN:            col(row, "vin"),
			Make:           col(row, "make"),
			Model:          col(row, "model"),
			Year:           year,
			MileageKm:      km,
			FuelType:       col(row, "fuel_type"),
			CurrentCountry: strings.ToUpper(col(row, "country")),
		})
	}
	return vehicles, nil
}

// ── Rendering ─────────────────────────────────────────────────────────────────

func renderDispositionPlan(plan *routesDispositionPlan) {
	fmt.Println()
	title := fmt.Sprintf("CARDEX ROUTES — %s %s %d  (%s)",
		plan.Make, plan.Model, plan.Year, plan.CurrentCountry)
	fmt.Println(styleBorder.Render(
		styleHeader.Render(title) + "\n" +
			field("VIN", orDash(plan.VehicleVIN)) +
			field("Mileage", fmt.Sprintf("%d km", plan.MileageKm)) +
			field("Current country", plan.CurrentCountry) +
			field("Routes evaluated", strconv.Itoa(len(plan.Routes))) +
			field("Total uplift", eurFmt(plan.TotalUplift)) +
			field("Computed at", plan.ComputedAt.Format("2006-01-02 15:04:05")),
	))

	fmt.Println()
	fmt.Println(styleHeader.Render("DISPOSITION ROUTES  (sorted by net profit)"))
	fmt.Printf("  %-4s %-4s %-14s %12s %10s %10s %12s  %5s  %s\n",
		styleBold.Render("FROM"),
		styleBold.Render("TO"),
		styleBold.Render("CHANNEL"),
		styleBold.Render("MARKET"),
		styleBold.Render("VAT"),
		styleBold.Render("TRANSPORT"),
		styleBold.Render("NET PROFIT"),
		styleBold.Render("DAYS"),
		styleBold.Render("NOTE"),
	)
	fmt.Println("  " + strings.Repeat("─", 90))

	for i, r := range plan.Routes {
		marker := ""
		if i == 0 {
			marker = styleGreen.Render("★ BEST")
		}
		netStyle := styleGreen
		if r.NetProfit < 0 {
			netStyle = styleRed
		}
		fmt.Printf("  %-4s %-4s %-14s %12s %10s %10s %12s  %5d  %s\n",
			r.FromCountry,
			styleCyan.Render(r.ToCountry),
			string(r.Channel),
			styleDim.Render(eurFmt(r.EstimatedPrice)),
			styleDim.Render("-"+eurFmt(r.VATCost)),
			styleDim.Render("-"+eurFmt(r.TransportCost)),
			netStyle.Render(eurFmt(r.NetProfit)),
			r.TimeToSellDays,
			marker,
		)
	}

	best := plan.BestRoute
	fmt.Println()
	fmt.Printf("  %s  Best: %s → %s via %s → net %s  (%d days to sell)\n",
		styleGreen.Render("★"),
		styleBold.Render(best.FromCountry),
		styleBold.Render(best.ToCountry),
		styleBold.Render(string(best.Channel)),
		styleGreen.Render(eurFmt(best.NetProfit)),
		best.TimeToSellDays,
	)
	if plan.TotalUplift > 0 {
		fmt.Printf("  %s  Uplift vs local worst: %s\n",
			styleGreen.Render("↑"),
			styleGreen.Render(eurFmt(plan.TotalUplift)),
		)
	}
	fmt.Println()
}

func renderMarketSpread(s *routesMarketSpread) {
	fmt.Println()
	title := fmt.Sprintf("MARKET SPREAD — %s %s %d  [%s]", s.Make, s.Model, s.Year, s.MileageBracket)
	fmt.Println(styleHeader.Render(title))
	fmt.Printf("  %-10s %12s %8s  %s\n",
		styleBold.Render("COUNTRY"),
		styleBold.Render("AVG PRICE"),
		styleBold.Render("SAMPLES"),
		styleBold.Render(""),
	)
	fmt.Println("  " + strings.Repeat("─", 40))

	for _, country := range []string{"DE", "FR", "ES", "NL", "BE", "CH"} {
		price, ok := s.PricesByCountry[country]
		if !ok {
			continue
		}
		samples := s.SamplesByCountry[country]
		marker := ""
		switch country {
		case s.BestCountry:
			marker = styleGreen.Render("▲ HIGHEST")
		case s.WorstCountry:
			marker = styleRed.Render("▼ LOWEST")
		}
		fmt.Printf("  %-10s %12s %8d  %s\n",
			country, eurFmt(price), samples, marker)
	}

	fmt.Println()
	fmt.Printf("  %s  Spread: %s  (best %s, worst %s)  confidence: %.0f%%\n",
		styleTeal.Render("◆"),
		styleOrange.Render(eurFmt(s.SpreadAmount)),
		styleGreen.Render(s.BestCountry),
		styleRed.Render(s.WorstCountry),
		s.Confidence*100,
	)
	fmt.Println()
}

func renderBatchSummary(plan *routesBatchPlan, total int) {
	fmt.Println()
	fmt.Println(styleHeader.Render("FLEET DISPOSITION PLAN SUMMARY"))
	fmt.Printf("  %-24s %s\n", styleBold.Render("Total vehicles:"), strconv.Itoa(total))
	fmt.Printf("  %-24s %s\n", styleBold.Render("Total est. uplift:"), styleGreen.Render(eurFmt(plan.TotalEstimatedUplift)))
	fmt.Printf("  %-24s %s\n", styleBold.Render("Avg uplift/vehicle:"), eurFmt(plan.AvgUpliftPerVehicle))
	fmt.Printf("  %-24s %d\n", styleBold.Render("Cap constraints applied:"), plan.CapConstraintApplied)
	fmt.Println()
	fmt.Println(styleHeader.Render("BY DESTINATION"))
	for country, count := range plan.ByDestination {
		pct := 0.0
		if total > 0 {
			pct = float64(count) / float64(total) * 100
		}
		fmt.Printf("  %-6s %4d vehicles  (%.0f%%)\n", country, count, pct)
	}
	fmt.Println()
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func eurFmt(cents int64) string {
	return fmt.Sprintf("€%.0f", float64(cents)/100)
}

func orDash(s string) string {
	if s == "" {
		return "—"
	}
	return s
}

// styleCyan is already defined in forecast.go — don't redeclare.
// Use styleTeal (defined in this file) for routes-specific accent color.
