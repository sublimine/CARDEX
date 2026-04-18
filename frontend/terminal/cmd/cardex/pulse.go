package main

// pulse.go — cardex pulse subcommands.
//
// Calls the pulse-service REST API (default: http://localhost:8504) and renders
// dealer health scores in an ANSI table.
//
//	cardex pulse show <dealer_id>
//	cardex pulse watchlist [--tier watch|stress|critical] [--country DE]

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

func pulseBaseURL() string {
	if u := os.Getenv("CARDEX_PULSE_URL"); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://localhost:8504"
}

type pulseScore struct {
	DealerID            string    `json:"dealer_id"`
	DealerName          string    `json:"dealer_name"`
	Country             string    `json:"country"`
	ActiveCount         int       `json:"active_listings"`
	LiquidationRatio    float64   `json:"liquidation_ratio"`
	PriceTrend          float64   `json:"price_trend_pct_week"`
	VolumeZScore        float64   `json:"volume_z_score"`
	AvgTimeOnMarket     float64   `json:"avg_time_on_market_days"`
	TimeOnMarketDelta   float64   `json:"time_on_market_delta_pct"`
	CompositeScoreDelta float64   `json:"composite_score_delta"`
	BrandHHI            float64   `json:"brand_hhi"`
	PriceVsMarket       float64   `json:"price_vs_market_ratio"`
	HealthScore         float64   `json:"health_score"`
	HealthTier          string    `json:"health_tier"`
	RiskSignals         []string  `json:"risk_signals"`
	TrendDirection      string    `json:"trend_direction"`
	ComputedAt          time.Time `json:"computed_at"`
}

type pulseHistoryPoint struct {
	DealerID    string    `json:"dealer_id"`
	HealthScore float64   `json:"health_score"`
	HealthTier  string    `json:"health_tier"`
	SignalsJSON string    `json:"signals_json"`
	ComputedAt  time.Time `json:"computed_at"`
}

type pulseWatchlistResponse struct {
	Dealers []pulseHistoryPoint `json:"dealers"`
	Total   int                 `json:"total"`
}

func newPulseCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "pulse",
		Short: "Dealer health score (CARDEX PULSE)",
	}
	cmd.AddCommand(newPulseShowCmd())
	cmd.AddCommand(newPulseWatchlistCmd())
	return cmd
}

func newPulseShowCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "show <dealer_id>",
		Short: "Show dealer health score",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return runPulseShow(args[0])
		},
	}
}

func runPulseShow(dealerID string) error {
	url := pulseBaseURL() + "/pulse/health/" + dealerID
	resp, err := http.Get(url) //nolint:noctx
	if err != nil {
		return fmt.Errorf("pulse service unavailable (%s): %w", pulseBaseURL(), err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("dealer %q not found", dealerID)
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("pulse service returned HTTP %d", resp.StatusCode)
	}

	var s pulseScore
	if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	printPulseCard(s)
	return nil
}

func printPulseCard(s pulseScore) {
	ts := pulseTierStyle(s.HealthTier)
	trendStr := pulseTrendIcon(s.TrendDirection)

	fmt.Printf("\n%s  %s  %s\n",
		styleHeader.Render("CARDEX PULSE"),
		styleBold.Render(s.DealerName),
		styleDim.Render("("+s.DealerID+")"),
	)
	fmt.Printf("Country: %s  |  Active listings: %d  |  Computed: %s\n\n",
		s.Country, s.ActiveCount,
		s.ComputedAt.Format("2006-01-02 15:04 UTC"),
	)

	scoreStr := fmt.Sprintf("%.1f / 100", s.HealthScore)
	fmt.Printf("Health Score:  %s   %s %s\n",
		ts.Render(scoreStr),
		ts.Render("["+strings.ToUpper(s.HealthTier)+"]"),
		trendStr,
	)
	fmt.Println()

	fmt.Printf("%-30s %s\n", styleBold.Render("Signal"), styleBold.Render("Value"))
	fmt.Println(strings.Repeat("─", 52))
	pulseSignalRow("Liquidation ratio (14d)",   fmt.Sprintf("%.2f", s.LiquidationRatio), s.LiquidationRatio > 1.5)
	pulseSignalRow("Price trend (%/week)",      fmt.Sprintf("%.1f%%", s.PriceTrend), s.PriceTrend < -5)
	pulseSignalRow("Volume z-score",            fmt.Sprintf("%.2f", s.VolumeZScore), pulseAbs(s.VolumeZScore) > 1.5)
	pulseSignalRow("Avg time on market (days)", fmt.Sprintf("%.0f d", s.AvgTimeOnMarket), s.TimeOnMarketDelta > 20)
	pulseSignalRow("ToM delta (% vs 30d)",      fmt.Sprintf("%.1f%%", s.TimeOnMarketDelta), s.TimeOnMarketDelta > 20)
	pulseSignalRow("Composite score delta",     fmt.Sprintf("%.1f pts", s.CompositeScoreDelta), s.CompositeScoreDelta < -10)
	pulseSignalRow("Brand HHI",                 fmt.Sprintf("%.3f", s.BrandHHI), s.BrandHHI > 0.5)
	pulseSignalRow("Price vs market",           fmt.Sprintf("%.3f", s.PriceVsMarket), s.PriceVsMarket > 0 && s.PriceVsMarket < 0.85)
	fmt.Println()

	if len(s.RiskSignals) > 0 {
		fmt.Printf("%s  %s\n", styleRed.Render("Active risk signals:"), strings.Join(s.RiskSignals, ", "))
	} else {
		fmt.Printf("%s\n", styleGreen.Render("No active risk signals"))
	}
	fmt.Println()
}

func pulseSignalRow(label, value string, stressed bool) {
	st := styleGreen
	if stressed {
		st = styleRed
	}
	fmt.Printf("  %-28s %s\n", label, st.Render(value))
}

func newPulseWatchlistCmd() *cobra.Command {
	var (
		tier    string
		country string
	)
	cmd := &cobra.Command{
		Use:   "watchlist",
		Short: "List dealers below health threshold",
		RunE: func(_ *cobra.Command, _ []string) error {
			return runPulseWatchlist(tier, country)
		},
	}
	cmd.Flags().StringVar(&tier, "tier", "watch", "health tier threshold: watch|stress|critical")
	cmd.Flags().StringVar(&country, "country", "", "filter by ISO-3166-1 country code (e.g. DE)")
	return cmd
}

func runPulseWatchlist(tier, country string) error {
	url := fmt.Sprintf("%s/pulse/watchlist?tier=%s", pulseBaseURL(), tier)
	if country != "" {
		url += "&country=" + country
	}

	resp, err := http.Get(url) //nolint:noctx
	if err != nil {
		return fmt.Errorf("pulse service unavailable (%s): %w", pulseBaseURL(), err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("pulse service returned HTTP %d", resp.StatusCode)
	}

	var wl pulseWatchlistResponse
	if err := json.NewDecoder(resp.Body).Decode(&wl); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	if wl.Total == 0 {
		fmt.Printf("%s\n", styleGreen.Render("No dealers in watchlist for the selected tier."))
		return nil
	}

	fmt.Printf("\n%s  (%d dealers, tier >= %s)\n\n",
		styleHeader.Render("PULSE WATCHLIST"), wl.Total, strings.ToUpper(tier))

	fmt.Printf("%-26s %-7s %-10s %-12s %s\n",
		styleBold.Render("Dealer ID"), styleBold.Render("Score"),
		styleBold.Render("Tier"), styleBold.Render("Computed"), styleBold.Render("Signals"),
	)
	fmt.Println(strings.Repeat("─", 90))

	for _, d := range wl.Dealers {
		ts := pulseTierStyle(d.HealthTier)
		signals := pulseSignalSummary(d.SignalsJSON)
		fmt.Printf("%-26s %-7s %-10s %-12s %s\n",
			d.DealerID,
			ts.Render(fmt.Sprintf("%.1f", d.HealthScore)),
			ts.Render(d.HealthTier),
			d.ComputedAt.Format("01-02 15:04"),
			styleDim.Render(signals),
		)
	}
	fmt.Println()
	return nil
}

func pulseTierStyle(tier string) lipgloss.Style {
	switch tier {
	case "healthy":
		return styleGreen
	case "watch":
		return styleYellow
	case "stress":
		return lipgloss.NewStyle().Foreground(lipgloss.Color("208"))
	case "critical":
		return styleRed
	default:
		return styleDim
	}
}

func pulseTrendIcon(dir string) string {
	switch dir {
	case "improving":
		return styleGreen.Render("↑ improving")
	case "deteriorating":
		return styleRed.Render("↓ deteriorating")
	default:
		return styleDim.Render("→ stable")
	}
}

func pulseSignalSummary(signalsJSON string) string {
	var signals []string
	if err := json.Unmarshal([]byte(signalsJSON), &signals); err != nil || len(signals) == 0 {
		return "none"
	}
	if len(signals) > 2 {
		return strings.Join(signals[:2], ",") + fmt.Sprintf(" +%d", len(signals)-2)
	}
	return strings.Join(signals, ",")
}

func pulseAbs(v float64) float64 {
	if v < 0 {
		return -v
	}
	return v
}
