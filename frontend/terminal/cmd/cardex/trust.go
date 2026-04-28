package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

// trustProfile mirrors the DealerTrustProfile JSON response from the trust service.
type trustProfile struct {
	DealerID          string    `json:"dealer_id"`
	DealerName        string    `json:"dealer_name"`
	Country           string    `json:"country"`
	VATID             string    `json:"vat_id"`
	VIESStatus        string    `json:"vies_status"`
	RegistryStatus    string    `json:"registry_status"`
	RegistryAge       int       `json:"registry_age_years"`
	V15Score          float64   `json:"v15_score"`
	ListingVolume     int       `json:"listing_volume"`
	AvgCompositeScore float64   `json:"avg_composite_score"`
	IndexTenureDays   int       `json:"index_tenure_days"`
	AnomalyCount      int       `json:"anomaly_count"`
	TrustScore        float64   `json:"trust_score"`
	TrustTier         string    `json:"trust_tier"`
	BadgeURL          string    `json:"badge_url"`
	IssuedAt          time.Time `json:"issued_at"`
	ExpiresAt         time.Time `json:"expires_at"`
	ProfileHash       string    `json:"profile_hash"`
	EIDASWalletDID    string    `json:"eidas_wallet_did,omitempty"`
}

func newTrustCmd() *cobra.Command {
	var trustURL string

	cmd := &cobra.Command{
		Use:   "trust",
		Short: "Dealer KYB trust profiles and portable badges",
		Long: `Queries the CARDEX Trust KYB service for dealer trust profiles.

Requires the trust service running (default: http://localhost:8505).
Start with: cd innovation/trust_kyb && go run ./cmd/trust-service/`,
	}

	cmd.PersistentFlags().StringVar(&trustURL, "trust-url",
		getEnvOrDefault("CARDEX_TRUST_URL", "http://localhost:8505"),
		"Trust service base URL (env: CARDEX_TRUST_URL)")

	cmd.AddCommand(newTrustShowCmd(&trustURL))
	cmd.AddCommand(newTrustListCmd(&trustURL))
	cmd.AddCommand(newTrustRefreshCmd(&trustURL))
	return cmd
}

// ── trust show ────────────────────────────────────────────────────────────────

func newTrustShowCmd(trustURL *string) *cobra.Command {
	return &cobra.Command{
		Use:     "show <dealer_id>",
		Short:   "Show full trust profile for a dealer",
		Args:    cobra.ExactArgs(1),
		Example: "  cardex trust show D_AUTOHAUS_001",
		RunE: func(_ *cobra.Command, args []string) error {
			return runTrustShow(*trustURL, args[0])
		},
	}
}

func runTrustShow(baseURL, dealerID string) error {
	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Get(baseURL + "/trust/profile/" + url.PathEscape(dealerID))
	if err != nil {
		return fmt.Errorf("trust service unavailable at %s: %w\nStart with: cd innovation/trust_kyb && go run ./cmd/trust-service/", baseURL, err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		var e map[string]string
		json.Unmarshal(body, &e)
		return fmt.Errorf("trust service error %d: %s", resp.StatusCode, e["error"])
	}

	var p trustProfile
	if err := json.Unmarshal(body, &p); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	renderTrustProfile(p)
	return nil
}

func renderTrustProfile(p trustProfile) {
	hdr := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39"))
	muted := lipgloss.NewStyle().Faint(true)

	tierStyle := trustTierStyle(p.TrustTier)
	tierBadge := tierStyle.Padding(0, 1).Render("  " + strings.ToUpper(p.TrustTier) + "  ")
	scoreStr := fmt.Sprintf("%.1f / 100", p.TrustScore)

	fmt.Println()
	fmt.Printf("  %s  %s  %s\n\n",
		hdr.Render("CARDEX TRUST PROFILE"),
		tierBadge,
		lipgloss.NewStyle().Bold(true).Render(scoreStr),
	)
	fmt.Printf("  %-22s %s\n", muted.Render("Dealer ID:"), p.DealerID)
	fmt.Printf("  %-22s %s\n", muted.Render("Name:"), p.DealerName)
	fmt.Printf("  %-22s %s\n", muted.Render("Country:"), p.Country)
	fmt.Printf("  %-22s %s\n", muted.Render("VAT ID:"), p.VATID)
	fmt.Println()
	fmt.Println("  " + hdr.Render("Signal Breakdown"))
	fmt.Printf("  %-22s %s  %s\n", muted.Render("VIES Status:"), statusIcon(p.VIESStatus), p.VIESStatus)
	fmt.Printf("  %-22s %s  %s (%d yrs)\n", muted.Render("Registry:"), statusIcon(p.RegistryStatus), p.RegistryStatus, p.RegistryAge)
	fmt.Printf("  %-22s %.1f\n", muted.Render("V15 Score:"), p.V15Score)
	fmt.Printf("  %-22s %d listings\n", muted.Render("Listing Volume:"), p.ListingVolume)
	fmt.Printf("  %-22s %.1f%%\n", muted.Render("Avg Composite:"), p.AvgCompositeScore)
	fmt.Printf("  %-22s %d days\n", muted.Render("Index Tenure:"), p.IndexTenureDays)
	fmt.Printf("  %-22s %d\n", muted.Render("Anomaly Signals:"), p.AnomalyCount)
	fmt.Println()
	fmt.Println("  " + hdr.Render("Credential"))
	fmt.Printf("  %-22s %s\n", muted.Render("Issued:"), p.IssuedAt.Format("2006-01-02 15:04 UTC"))
	fmt.Printf("  %-22s %s\n", muted.Render("Expires:"), p.ExpiresAt.Format("2006-01-02 15:04 UTC"))
	fmt.Printf("  %-22s %s\n", muted.Render("Hash:"), p.ProfileHash[:16]+"…")
	fmt.Printf("  %-22s %s\n", muted.Render("Badge URL:"), muted.Render(p.BadgeURL))
	if p.EIDASWalletDID != "" {
		fmt.Printf("  %-22s %s\n", muted.Render("eIDAS DID:"), p.EIDASWalletDID)
	}
	fmt.Println()
}

// ── trust list ────────────────────────────────────────────────────────────────

func newTrustListCmd(trustURL *string) *cobra.Command {
	var (
		tier    string
		country string
		limit   int
	)
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List dealer trust profiles, optionally filtered by tier or country",
		Example: `  cardex trust list --tier platinum --country DE
  cardex trust list --country FR --limit 20`,
		RunE: func(_ *cobra.Command, _ []string) error {
			return runTrustList(*trustURL, tier, country, limit)
		},
	}
	cmd.Flags().StringVar(&tier, "tier", "", "filter by trust tier (platinum|gold|silver|unverified)")
	cmd.Flags().StringVar(&country, "country", "", "filter by ISO-3166-1 country code")
	cmd.Flags().IntVar(&limit, "limit", 25, "max results")
	return cmd
}

func runTrustList(baseURL, tier, country string, limit int) error {
	q := url.Values{}
	if tier != "" {
		q.Set("tier", tier)
	}
	if country != "" {
		q.Set("country", country)
	}
	if limit > 0 {
		q.Set("limit", fmt.Sprintf("%d", limit))
	}
	endpoint := baseURL + "/trust/list"
	if len(q) > 0 {
		endpoint += "?" + q.Encode()
	}

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Get(endpoint)
	if err != nil {
		return fmt.Errorf("trust service unavailable at %s: %w", baseURL, err)
	}
	defer resp.Body.Close()

	var result struct {
		Count    int            `json:"count"`
		Profiles []trustProfile `json:"profiles"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	hdr := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39"))
	muted := lipgloss.NewStyle().Faint(true)

	fmt.Println()
	fmt.Printf("  %s  (%d results)\n\n", hdr.Render("DEALER TRUST PROFILES"), result.Count)
	fmt.Printf("  %-12s %-30s %-8s %-12s %7s  %s\n",
		"TIER", "NAME", "COUNTRY", "VAT ID", "SCORE", "EXPIRES")
	fmt.Println("  " + strings.Repeat("─", 80))

	for _, p := range result.Profiles {
		tierBadge := trustTierStyle(p.TrustTier).Render(fmt.Sprintf("%-11s", strings.ToUpper(p.TrustTier)))
		name := p.DealerName
		if len(name) > 28 {
			name = name[:25] + "..."
		}
		expires := p.ExpiresAt.Format("2006-01-02")
		fmt.Printf("  %s %-30s %-8s %-12s %6.1f  %s\n",
			tierBadge, name, p.Country, p.VATID, p.TrustScore, muted.Render(expires))
	}
	fmt.Println()
	return nil
}

// ── trust refresh ─────────────────────────────────────────────────────────────

func newTrustRefreshCmd(trustURL *string) *cobra.Command {
	return &cobra.Command{
		Use:     "refresh <dealer_id>",
		Short:   "Force-recompute trust profile for a dealer",
		Args:    cobra.ExactArgs(1),
		Example: "  cardex trust refresh D_AUTOHAUS_001",
		RunE: func(_ *cobra.Command, args []string) error {
			return runTrustRefresh(*trustURL, args[0])
		},
	}
}

func runTrustRefresh(baseURL, dealerID string) error {
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Post(
		baseURL+"/trust/refresh/"+url.PathEscape(dealerID),
		"application/json",
		bytes.NewReader(nil),
	)
	if err != nil {
		return fmt.Errorf("trust service unavailable at %s: %w", baseURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var e map[string]string
		json.NewDecoder(resp.Body).Decode(&e)
		return fmt.Errorf("trust service error %d: %s", resp.StatusCode, e["error"])
	}

	var p trustProfile
	if err := json.NewDecoder(resp.Body).Decode(&p); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	fmt.Printf("Trust profile recomputed for %s — tier: %s, score: %.1f\n",
		dealerID, p.TrustTier, p.TrustScore)
	renderTrustProfile(p)
	return nil
}

// ── rendering helpers ─────────────────────────────────────────────────────────

func trustTierStyle(tier string) lipgloss.Style {
	switch tier {
	case "platinum":
		return lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("220"))
	case "gold":
		return lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("250"))
	case "silver":
		return lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("130"))
	default:
		return lipgloss.NewStyle().Faint(true)
	}
}

func statusIcon(s string) string {
	switch s {
	case "valid", "registered":
		return styleGreen.Render("✓")
	case "invalid", "not_found":
		return styleRed.Render("✗")
	default:
		return styleYellow.Render("?")
	}
}
