package main

import (
	"database/sql"
	"fmt"
	"math"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

// ── Styles (ev-watch specific) ────────────────────────────────────────────────

var (
	styleEVHeader   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("51"))
	styleEVWarn     = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
	styleEVDanger   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("196"))
	styleEVNormal   = lipgloss.NewStyle().Foreground(lipgloss.Color("82"))
)

// ── EV Watch command group ─────────────────────────────────────────────────────

func newEVWatchCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "ev-watch",
		Short: "Battery anomaly signals for EV listings",
		Long: `ev-watch detects EV listings with unusually low prices relative to their
mileage cohort — a proxy for State-of-Health (SoH) degradation.

Methodology: OLS regression (price ~ mileage_km) per cohort (make+model+year+country).
Z-score of residual < -1.5 → anomaly flag.  Z < -2.0 → suspected battery degradation.`,
	}

	cmd.AddCommand(newEVWatchListCmd())
	cmd.AddCommand(newEVWatchCohortCmd())
	return cmd
}

// ── cardex ev-watch list ──────────────────────────────────────────────────────

func newEVWatchListCmd() *cobra.Command {
	var (
		country      string
		make_        string
		model        string
		year         int
		minConfidence float64
		limit        int
		allListings  bool
	)

	cmd := &cobra.Command{
		Use:   "list",
		Short: "List EV listings with battery anomaly signals",
		Example: `  cardex ev-watch list --country DE --make Tesla
  cardex ev-watch list --make Tesla --model "Model 3" --year 2021 --min-confidence 0.7
  cardex ev-watch list --all`,
		RunE: func(_ *cobra.Command, _ []string) error {
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			return runEVWatchList(db, country, make_, model, year, minConfidence, limit, allListings)
		},
	}

	cmd.Flags().StringVar(&country, "country", "", "ISO country code (DE, FR, ES, …)")
	cmd.Flags().StringVar(&make_, "make", "", "vehicle make (case-insensitive)")
	cmd.Flags().StringVar(&model, "model", "", "vehicle model (partial match)")
	cmd.Flags().IntVar(&year, "year", 0, "model year")
	cmd.Flags().Float64Var(&minConfidence, "min-confidence", 0, "minimum confidence score [0–1]")
	cmd.Flags().IntVar(&limit, "limit", 50, "maximum rows to display")
	cmd.Flags().BoolVar(&allListings, "all", false, "show all listings (not just anomalies)")
	return cmd
}

func runEVWatchList(db *sql.DB,
	country, make_, model string, year int,
	minConf float64, limit int, all bool,
) error {
	var conds []string
	var args []any

	if !all {
		conds = append(conds, "anomaly_flag = 1")
	}
	if country != "" {
		conds = append(conds, "country = UPPER(?)")
		args = append(args, country)
	}
	if make_ != "" {
		conds = append(conds, "make = UPPER(?)")
		args = append(args, make_)
	}
	if model != "" {
		conds = append(conds, "model LIKE UPPER(?)")
		args = append(args, "%"+strings.ToUpper(model)+"%")
	}
	if year > 0 {
		conds = append(conds, "year = ?")
		args = append(args, year)
	}
	if minConf > 0 {
		conds = append(conds, "confidence >= ?")
		args = append(args, minConf)
	}

	where := ""
	if len(conds) > 0 {
		where = "WHERE " + strings.Join(conds, " AND ")
	}
	args = append(args, limit)

	rows, err := db.Query(fmt.Sprintf(`
		SELECT vehicle_id, COALESCE(vin,''), make, model, year, country,
		       price_cents, mileage_km, cohort_size, z_score,
		       anomaly_flag, confidence, estimated_soh, detected_at
		FROM ev_anomaly_scores
		%s ORDER BY z_score ASC LIMIT ?`, where), args...)
	if err != nil {
		return fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	type evRow struct {
		id, vin, make, model, country, soh, detectedAt string
		year, mileage, cohortSize                       int
		priceCents                                      int64
		zScore, confidence                              float64
		anomalyFlag                                     bool
	}

	var results []evRow
	for rows.Next() {
		var r evRow
		var flagInt int
		if err := rows.Scan(
			&r.id, &r.vin, &r.make, &r.model, &r.year, &r.country,
			&r.priceCents, &r.mileage, &r.cohortSize,
			&r.zScore, &flagInt, &r.confidence, &r.soh, &r.detectedAt,
		); err != nil {
			return err
		}
		r.anomalyFlag = flagInt == 1
		results = append(results, r)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	if len(results) == 0 {
		fmt.Println(styleDim.Render("No EV anomalies found. Run the quality service to populate ev_anomaly_scores."))
		return nil
	}

	hdr := fmt.Sprintf("%-24s %-8s %-10s %-18s %5s %8s %7s %6s %6s  %s",
		"ID", "COUNTRY", "MAKE", "MODEL", "YEAR", "PRICE€", "KM", "ZSCORE", "CONF", "SOH")
	fmt.Println(styleEVHeader.Render(hdr))
	fmt.Println(strings.Repeat("─", 100))

	for _, r := range results {
		zStr  := fmt.Sprintf("%+.2f", r.zScore)
		confStr := fmt.Sprintf("%.2f", r.confidence)
		priceStr := fmt.Sprintf("%8.0f", float64(r.priceCents)/100)
		line := fmt.Sprintf("%-24s %-8s %-10s %-18s %5d %s %7d %6s %6s  %s",
			r.id, r.country, r.make, r.model, r.year,
			priceStr, r.mileage, zStr, confStr,
			sohStyle(r.soh))
		fmt.Println(line)
	}
	fmt.Printf("\n%s\n", styleDim.Render(fmt.Sprintf("%d listing(s)  (use --all to see non-anomalies)", len(results))))
	return nil
}

// ── cardex ev-watch cohort ────────────────────────────────────────────────────

func newEVWatchCohortCmd() *cobra.Command {
	var (
		make_   string
		model   string
		year    int
		country string
	)

	cmd := &cobra.Command{
		Use:   "cohort",
		Short: "Show cohort statistics for a specific make/model",
		Example: `  cardex ev-watch cohort --make Tesla --model "Model 3" --year 2021 --country DE`,
		RunE: func(_ *cobra.Command, _ []string) error {
			if make_ == "" || model == "" {
				return fmt.Errorf("--make and --model are required")
			}
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			return runEVWatchCohort(db, make_, model, year, country)
		},
	}

	cmd.Flags().StringVar(&make_, "make", "", "vehicle make (required)")
	cmd.Flags().StringVar(&model, "model", "", "vehicle model (required)")
	cmd.Flags().IntVar(&year, "year", 0, "model year (0 = all years)")
	cmd.Flags().StringVar(&country, "country", "", "ISO country code (empty = all countries)")
	_ = cmd.MarkFlagRequired("make")
	_ = cmd.MarkFlagRequired("model")
	return cmd
}

func runEVWatchCohort(db *sql.DB, make_, model string, year int, country string) error {
	var conds = []string{"make = UPPER(?)", "model = UPPER(?)"}
	var args = []any{make_, model}
	if year > 0 {
		conds = append(conds, "year = ?")
		args = append(args, year)
	}
	if country != "" {
		conds = append(conds, "country = UPPER(?)")
		args = append(args, country)
	}
	where := "WHERE " + strings.Join(conds, " AND ")

	row := db.QueryRow(fmt.Sprintf(`
		SELECT
			COUNT(*),
			AVG(price_cents) / 100.0,
			AVG(cohort_std_dev),
			MIN(price_cents) / 100.0,
			MAX(price_cents) / 100.0,
			SUM(CASE WHEN anomaly_flag = 1 THEN 1 ELSE 0 END),
			SUM(CASE WHEN z_score < -2.0 THEN 1 ELSE 0 END),
			AVG(mileage_km),
			MAX(detected_at)
		FROM ev_anomaly_scores %s`, where), args...)

	var (
		count, anomalyCount, severeCount       int
		meanPrice, stdDev, minP, maxP, avgMile float64
		detectedAt                              sql.NullString
	)
	if err := row.Scan(&count, &meanPrice, &stdDev, &minP, &maxP,
		&anomalyCount, &severeCount, &avgMile, &detectedAt); err != nil {
		if err == sql.ErrNoRows || count == 0 {
			fmt.Println(styleDim.Render("No cohort data found. Run the quality service to populate ev_anomaly_scores."))
			return nil
		}
		return fmt.Errorf("query: %w", err)
	}

	fmt.Println()
	title := fmt.Sprintf("EV COHORT: %s %s", strings.ToUpper(make_), strings.ToUpper(model))
	if year > 0 {
		title += fmt.Sprintf(" %d", year)
	}
	if country != "" {
		title += fmt.Sprintf(" [%s]", strings.ToUpper(country))
	}
	fmt.Println(styleEVHeader.Render(title))
	fmt.Println(strings.Repeat("─", 60))
	fmt.Printf("  %-24s %d\n", styleBold.Render("Listings analysed:"), count)
	fmt.Printf("  %-24s €%.0f\n", styleBold.Render("Mean price:"), meanPrice)
	fmt.Printf("  %-24s €%.0f\n", styleBold.Render("Std deviation:"), stdDev)
	fmt.Printf("  %-24s €%.0f – €%.0f\n", styleBold.Render("Price range:"), minP, maxP)
	fmt.Printf("  %-24s %.0f km\n", styleBold.Render("Avg mileage:"), avgMile)

	anomalyPct := 0.0
	if count > 0 {
		anomalyPct = float64(anomalyCount) / float64(count) * 100
	}
	anomalyStr := fmt.Sprintf("%d (%.1f%%)", anomalyCount, anomalyPct)
	severeStr := fmt.Sprintf("%d", severeCount)

	fmt.Printf("  %-24s %s\n", styleBold.Render("Anomalies (z < -1.5):"),
		styleEVWarn.Render(anomalyStr))
	if severeCount > 0 {
		fmt.Printf("  %-24s %s\n", styleBold.Render("Severe (z < -2.0):"),
			styleEVDanger.Render(severeStr))
	}

	// Simple ASCII histogram of z-score distribution
	histRows, err := db.Query(fmt.Sprintf(`
		SELECT z_score FROM ev_anomaly_scores %s ORDER BY z_score`, where), args...)
	if err == nil {
		defer histRows.Close()
		var zScores []float64
		for histRows.Next() {
			var z float64
			if histRows.Scan(&z) == nil {
				zScores = append(zScores, z)
			}
		}
		if len(zScores) > 0 {
			fmt.Println()
			fmt.Println(styleDim.Render("  Z-score distribution:"))
			printZHistogram(zScores)
		}
	}

	fmt.Printf("\n  %s %s\n", styleDim.Render("Last computed:"), detectedAt.String)
	fmt.Println()
	return nil
}

// printZHistogram renders a compact ASCII histogram of z-scores.
func printZHistogram(zScores []float64) {
	buckets := []struct{ lo, hi float64; label string }{
		{math.Inf(-1), -3.0, "< -3.0"},
		{-3.0, -2.0, "-3.0 to -2.0"},
		{-2.0, -1.5, "-2.0 to -1.5"},
		{-1.5, -0.5, "-1.5 to -0.5"},
		{-0.5, 0.5, "-0.5 to +0.5"},
		{0.5, 1.5, "+0.5 to +1.5"},
		{1.5, math.Inf(1), "> +1.5"},
	}
	counts := make([]int, len(buckets))
	for _, z := range zScores {
		for i, b := range buckets {
			if z >= b.lo && z < b.hi {
				counts[i]++
				break
			}
		}
	}
	maxCount := 0
	for _, c := range counts {
		if c > maxCount {
			maxCount = c
		}
	}
	barWidth := 30
	for i, b := range buckets {
		n := counts[i]
		width := 0
		if maxCount > 0 {
			width = int(float64(n) / float64(maxCount) * float64(barWidth))
		}
		bar := strings.Repeat("█", width)
		style := styleEVNormal
		if b.hi <= -1.5 {
			style = styleEVWarn
		}
		if b.hi <= -2.0 {
			style = styleEVDanger
		}
		fmt.Printf("  %-14s %s %s %d\n",
			styleDim.Render(b.label),
			style.Render(bar),
			styleDim.Render(strings.Repeat("·", barWidth-width)),
			n)
	}
}

func sohStyle(soh string) string {
	switch soh {
	case "suspicious":
		return styleEVDanger.Render("🔴 suspicious")
	case "below_average":
		return styleEVWarn.Render("🟡 below_avg ")
	default:
		return styleEVNormal.Render("🟢 normal    ")
	}
}
