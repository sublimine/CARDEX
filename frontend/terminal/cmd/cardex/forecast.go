package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

// ── Styles (forecast-specific) ────────────────────────────────────────────────

var (
	styleCyan   = lipgloss.NewStyle().Foreground(lipgloss.Color("51"))
	styleMagenta = lipgloss.NewStyle().Foreground(lipgloss.Color("207"))
)

// ── API types ─────────────────────────────────────────────────────────────────

type forecastRequest struct {
	Make        string `json:"make"`
	Model       string `json:"model"`
	YearRange   string `json:"year_range"`
	Country     string `json:"country"`
	HorizonDays int    `json:"horizon_days"`
}

type forecastPoint struct {
	Date string  `json:"date"`
	P10  float64 `json:"p10"`
	P50  float64 `json:"p50"`
	P90  float64 `json:"p90"`
}

type backtestMetrics struct {
	MASE      *float64 `json:"mase"`
	SMAPE     *float64 `json:"smape"`
	HeldOutN  int      `json:"held_out_n"`
}

type forecastResponse struct {
	SeriesKey        string          `json:"series_key"`
	HorizonDays      int             `json:"horizon_days"`
	Backend          string          `json:"backend"`
	Model            string          `json:"model"`
	SeriesLength     int             `json:"series_length"`
	LastDate         string          `json:"last_date"`
	LastPrice        float64         `json:"last_price"`
	InferenceSeconds float64         `json:"inference_seconds"`
	Forecast         []forecastPoint `json:"forecast"`
	Backtest         backtestMetrics `json:"backtest"`
}

type apiError struct {
	Detail interface{} `json:"detail"`
}

// ── Flag vars ─────────────────────────────────────────────────────────────────

var (
	flagForecastMake    string
	flagForecastModel   string
	flagForecastYearMin int
	flagForecastYearMax int
	flagForecastCountry string
	flagForecastHorizon int
	flagForecastURL     string
	flagForecastSpark   bool
)

// ── Command ───────────────────────────────────────────────────────────────────

func newForecastCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "forecast",
		Short: "Forecast vehicle prices via the Chronos-2 service",
		Example: `  cardex forecast --make BMW --model "3er" --year-min 2018 --year-max 2020 --country DE --horizon 30
  cardex forecast --make Renault --model "Clio" --year-min 2019 --year-max 2021 --country FR --horizon 60 --spark`,
		RunE: runForecast,
	}

	cmd.Flags().StringVar(&flagForecastMake, "make", "", "vehicle make (required)")
	cmd.Flags().StringVar(&flagForecastModel, "model", "", "vehicle model (required)")
	cmd.Flags().IntVar(&flagForecastYearMin, "year-min", 0, "year range start (required)")
	cmd.Flags().IntVar(&flagForecastYearMax, "year-max", 0, "year range end (required)")
	cmd.Flags().StringVar(&flagForecastCountry, "country", "DE", "ISO country code")
	cmd.Flags().IntVar(&flagForecastHorizon, "horizon", 30, "forecast horizon in days (1–365)")
	cmd.Flags().StringVar(&flagForecastURL, "url", "", "forecast service URL (env: FORECAST_URL, default: http://localhost:8503)")
	cmd.Flags().BoolVar(&flagForecastSpark, "spark", false, "render ASCII sparkline of p50 forecast")

	_ = cmd.MarkFlagRequired("make")
	_ = cmd.MarkFlagRequired("model")
	_ = cmd.MarkFlagRequired("year-min")
	_ = cmd.MarkFlagRequired("year-max")

	return cmd
}

func runForecast(_ *cobra.Command, _ []string) error {
	serviceURL := flagForecastURL
	if serviceURL == "" {
		if v := os.Getenv("FORECAST_URL"); v != "" {
			serviceURL = v
		} else {
			serviceURL = "http://localhost:8503"
		}
	}

	yearRange := fmt.Sprintf("%d-%d", flagForecastYearMin, flagForecastYearMax)

	req := forecastRequest{
		Make:        flagForecastMake,
		Model:       flagForecastModel,
		YearRange:   yearRange,
		Country:     flagForecastCountry,
		HorizonDays: flagForecastHorizon,
	}

	resp, err := callForecastAPI(serviceURL, req)
	if err != nil {
		return err
	}

	renderForecast(resp)
	return nil
}

// ── HTTP client ───────────────────────────────────────────────────────────────

func callForecastAPI(baseURL string, req forecastRequest) (*forecastResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	client := &http.Client{Timeout: 120 * time.Second}
	httpResp, err := client.Post(baseURL+"/forecast", "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("forecast service unreachable (%s): %w\n\nStart with: uvicorn serve:app --port 8503", baseURL, err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode == http.StatusNotFound {
		var apiErr apiError
		_ = json.NewDecoder(httpResp.Body).Decode(&apiErr)
		return nil, fmt.Errorf("series not found — no CSV for %s/%s/%s/%s\n%v",
			req.Country, req.Make, req.Model, req.YearRange, apiErr.Detail)
	}
	if httpResp.StatusCode == http.StatusUnprocessableEntity {
		var apiErr apiError
		_ = json.NewDecoder(httpResp.Body).Decode(&apiErr)
		return nil, fmt.Errorf("validation error: %v", apiErr.Detail)
	}
	if httpResp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("forecast service returned HTTP %d", httpResp.StatusCode)
	}

	var resp forecastResponse
	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &resp, nil
}

// ── Rendering ─────────────────────────────────────────────────────────────────

func renderForecast(r *forecastResponse) {
	if len(r.Forecast) == 0 {
		fmt.Println(styleRed.Render("No forecast points returned."))
		return
	}

	last := r.Forecast[len(r.Forecast)-1]
	mid := r.Forecast[len(r.Forecast)/2]

	trend, trendStyle := trendIndicator(r.LastPrice, last.P50)

	// ── Header ──
	fmt.Println()
	title := fmt.Sprintf("CARDEX PRICE FORECAST — %s %s %s (%s)",
		r.SeriesKey, styleYellow.Render(fmt.Sprintf("+%dd", r.HorizonDays)),
		trend, styleDim.Render(r.Backend))
	fmt.Println(styleBorder.Render(
		styleHeader.Render(title) + "\n" +
			field("Series", r.SeriesKey) +
			field("Last date", r.LastDate) +
			field("Last price", styleBold.Render(fmt.Sprintf("€%.0f", r.LastPrice))) +
			field("Horizon", fmt.Sprintf("%d days → %s", r.HorizonDays, last.Date)) +
			field("Backend", r.Backend) +
			field("Inference", fmt.Sprintf("%.2fs", r.InferenceSeconds)) +
			field("Series length", fmt.Sprintf("%d days", r.SeriesLength)),
	))

	// ── Forecast table ──
	fmt.Println()
	fmt.Println(styleHeader.Render("PRICE FORECAST"))
	fmt.Printf("  %-12s %11s %11s %11s   %s\n",
		styleBold.Render("DATE"),
		styleBold.Render("P10"),
		styleBold.Render("P50 (median)"),
		styleBold.Render("P90"),
		styleBold.Render("BAND"),
	)
	fmt.Println("  " + strings.Repeat("─", 70))

	// Print selected rows: first, mid, last (or all if horizon ≤ 10)
	indices := forecastIndices(len(r.Forecast))
	for _, i := range indices {
		pt := r.Forecast[i]
		band := pt.P90 - pt.P10
		marker := ""
		if i == len(r.Forecast)-1 {
			marker = trendStyle.Render(" " + trend)
		}
		fmt.Printf("  %-12s %s %s %s   €%-8.0f%s\n",
			pt.Date,
			styleDim.Render(fmt.Sprintf("€%8.0f", pt.P10)),
			styleCyan.Render(fmt.Sprintf("€%8.0f", pt.P50)),
			styleDim.Render(fmt.Sprintf("€%8.0f", pt.P90)),
			band, marker,
		)
	}
	_ = mid // used implicitly via indices

	// ── Summary ──
	fmt.Println()
	changePct := (last.P50 - r.LastPrice) / r.LastPrice * 100
	changeSign := "+"
	if changePct < 0 {
		changeSign = ""
	}
	fmt.Printf("  %s  Current: %s → %s in %dd (%s%s%%)\n",
		trendStyle.Render(trend),
		styleBold.Render(fmt.Sprintf("€%.0f", r.LastPrice)),
		styleBold.Render(fmt.Sprintf("€%.0f", last.P50)),
		r.HorizonDays,
		changeSign, fmt.Sprintf("%.1f", changePct),
	)
	fmt.Printf("  %s  90%% CI: €%.0f – €%.0f (band: €%.0f)\n",
		strings.Repeat(" ", 2),
		last.P10, last.P90, last.P90-last.P10,
	)

	// ── Sparkline ──
	if flagForecastSpark {
		fmt.Println()
		fmt.Println(styleHeader.Render("P50 SPARKLINE"))
		fmt.Println("  " + sparkline(r.Forecast))
		fmt.Printf("  %s ← %s → %s\n",
			styleDim.Render(r.LastDate),
			strings.Repeat(" ", max(0, len(r.Forecast)/2-5)),
			styleDim.Render(last.Date),
		)
	}

	// ── Backtest ──
	fmt.Println()
	fmt.Println(styleHeader.Render("BACKTEST METRICS"))
	bt := r.Backtest
	maseStr := styleDim.Render("n/a")
	if bt.MASE != nil {
		maseStr = maseStyle(*bt.MASE)
	}
	smapeStr := styleDim.Render("n/a")
	if bt.SMAPE != nil {
		smapeStr = fmt.Sprintf("%.1f%%", *bt.SMAPE)
	}
	fmt.Printf("  %-20s %s\n", styleBold.Render("MASE:"), maseStr)
	fmt.Printf("  %-20s %s\n", styleBold.Render("sMAPE:"), smapeStr)
	fmt.Printf("  %-20s %d days\n", styleBold.Render("Held-out window:"), bt.HeldOutN)
	if bt.MASE != nil {
		if *bt.MASE < 1.0 {
			fmt.Printf("  %s model beats naïve baseline (MASE < 1)\n", styleGreen.Render("✓"))
		} else {
			fmt.Printf("  %s model does not beat naïve baseline (MASE ≥ 1)\n", styleYellow.Render("⚠"))
		}
	}
	fmt.Println()
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func trendIndicator(lastPrice, forecastedP50 float64) (string, lipgloss.Style) {
	if lastPrice == 0 {
		return "→", styleYellow
	}
	pct := (forecastedP50 - lastPrice) / lastPrice * 100
	switch {
	case pct > 2.0:
		return "↑", styleGreen
	case pct < -2.0:
		return "↓", styleRed
	default:
		return "→", styleYellow
	}
}

func maseStyle(mase float64) string {
	s := fmt.Sprintf("%.3f", mase)
	if mase < 0.8 {
		return styleGreen.Render(s)
	}
	if mase < 1.0 {
		return styleYellow.Render(s)
	}
	return styleRed.Render(s)
}

// forecastIndices returns the row indices to display in the forecast table.
// For short horizons (≤ 14) all rows are shown; for longer ones, up to 10 rows
// are sampled evenly plus the final row.
func forecastIndices(n int) []int {
	if n <= 14 {
		idx := make([]int, n)
		for i := range idx {
			idx[i] = i
		}
		return idx
	}
	// Sample ~8 evenly-spaced rows + last
	step := n / 8
	var idx []int
	for i := 0; i < n-1; i += step {
		idx = append(idx, i)
	}
	if idx[len(idx)-1] != n-1 {
		idx = append(idx, n-1)
	}
	return idx
}

// sparkline renders a compact Unicode block-character chart of p50 values.
func sparkline(pts []forecastPoint) string {
	const blocks = "▁▂▃▄▅▆▇█"
	runes := []rune(blocks)
	nBlocks := len(runes)

	vals := make([]float64, len(pts))
	minV, maxV := math.MaxFloat64, -math.MaxFloat64
	for i, pt := range pts {
		vals[i] = pt.P50
		if pt.P50 < minV {
			minV = pt.P50
		}
		if pt.P50 > maxV {
			maxV = pt.P50
		}
	}

	span := maxV - minV
	var sb strings.Builder
	for _, v := range vals {
		var idx int
		if span > 0 {
			idx = int((v-minV)/span*float64(nBlocks-1) + 0.5)
		}
		if idx < 0 {
			idx = 0
		}
		if idx >= nBlocks {
			idx = nBlocks - 1
		}
		sb.WriteRune(runes[idx])
	}
	return styleCyan.Render(sb.String()) +
		styleDim.Render(fmt.Sprintf("  €%.0f–€%.0f", minV, maxV))
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// trendStyle is a package-level var only used inside renderForecast via the
// returned lipgloss.Style from trendIndicator. Declared here to satisfy the
// styleMagenta usage (kept for future use).
var _ = styleMagenta
