package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

func newTaxCmd() *cobra.Command {
	var (
		fromCountry string
		toCountry   string
		priceEUR    float64
		marginEUR   float64
		sellerVAT   string
		buyerVAT    string
		ageMonths   int
		vehicleKM   int
		taxURL      string
	)

	cmd := &cobra.Command{
		Use:   "tax",
		Short: "VAT cross-border optimiser for used-vehicle B2B transactions",
		Long: `Calculates the optimal VAT route for a used-vehicle transaction between
two countries (DE/FR/ES/BE/NL/CH). Returns all applicable regimes ordered by
effective cost, with the optimal route highlighted.

Requires the tax engine server running (default: http://localhost:8504).
Start with: cd innovation/tax_engine && go run ./cmd/tax-server/`,
		Example: `  cardex tax --from ES --to DE --price 15000 --margin 2000 \
    --seller-vat ESB12345678 --buyer-vat DE123456789

  cardex tax --from DE --to CH --price 25000
  cardex tax --from CH --to FR --price 18000 --age-months 4`,
		RunE: func(cmd *cobra.Command, args []string) error {
			priceCents := int64(priceEUR * 100)
			marginCents := int64(marginEUR * 100)

			body := map[string]interface{}{
				"from_country":        strings.ToUpper(fromCountry),
				"to_country":          strings.ToUpper(toCountry),
				"vehicle_price_cents": priceCents,
				"margin_cents":        marginCents,
				"seller_vat_id":       sellerVAT,
				"buyer_vat_id":        buyerVAT,
				"vehicle_age_months":  ageMonths,
				"vehicle_km":          vehicleKM,
			}
			payload, _ := json.Marshal(body)

			endpoint := taxURL + "/tax/calculate"
			client := &http.Client{Timeout: 20 * time.Second}
			resp, err := client.Post(endpoint, "application/json", bytes.NewReader(payload))
			if err != nil {
				return fmt.Errorf("tax server unavailable at %s: %w\nStart with: cd innovation/tax_engine && go run ./cmd/tax-server/", endpoint, err)
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				var errBody map[string]string
				json.NewDecoder(resp.Body).Decode(&errBody)
				return fmt.Errorf("tax server error %d: %s", resp.StatusCode, errBody["error"])
			}

			var result taxResponse
			if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
				return fmt.Errorf("decode response: %w", err)
			}

			renderTaxTable(result)
			return nil
		},
	}

	cmd.Flags().StringVar(&fromCountry, "from", "", "Seller country (DE/FR/ES/BE/NL/CH) [required]")
	cmd.Flags().StringVar(&toCountry, "to", "", "Buyer country (DE/FR/ES/BE/NL/CH) [required]")
	cmd.Flags().Float64Var(&priceEUR, "price", 0, "Vehicle price in EUR [required]")
	cmd.Flags().Float64Var(&marginEUR, "margin", 0, "Dealer margin in EUR (default: 20% of price)")
	cmd.Flags().StringVar(&sellerVAT, "seller-vat", "", "Seller EU VAT ID (e.g. ESB12345678)")
	cmd.Flags().StringVar(&buyerVAT, "buyer-vat", "", "Buyer EU VAT ID (e.g. DE123456789)")
	cmd.Flags().IntVar(&ageMonths, "age-months", 0, "Vehicle age in months (Art. 2(2)(b) check)")
	cmd.Flags().IntVar(&vehicleKM, "km", 0, "Vehicle mileage in km (Art. 2(2)(b) check)")
	cmd.Flags().StringVar(&taxURL, "tax-url", getEnvOrDefault("CARDEX_TAX_URL", "http://localhost:8504"), "Tax engine URL")

	cmd.MarkFlagRequired("from")
	cmd.MarkFlagRequired("to")
	cmd.MarkFlagRequired("price")

	return cmd
}

type taxResponse struct {
	FromCountry  string          `json:"from_country"`
	ToCountry    string          `json:"to_country"`
	VehiclePrice int64           `json:"vehicle_price_cents"`
	IsNewVehicle bool            `json:"is_new_vehicle"`
	VIESStatus   map[string]bool `json:"vies_status"`
	Routes       []taxCalc       `json:"Routes"`
	OptimalRoute *taxCalc        `json:"optimal_route"`
}

type taxCalc struct {
	Route struct {
		FromCountry string  `json:"FromCountry"`
		ToCountry   string  `json:"ToCountry"`
		Regime      string  `json:"Regime"`
		VATRate     float64 `json:"VATRate"`
		LegalBasis  string  `json:"LegalBasis"`
	} `json:"Route"`
	VehiclePrice int64  `json:"VehiclePrice"`
	MarginAmount int64  `json:"MarginAmount"`
	TaxableBase  int64  `json:"TaxableBase"`
	VATAmount    int64  `json:"VATAmount"`
	TotalCost    int64  `json:"TotalCost"`
	NetSaving    int64  `json:"NetSaving"`
	IsOptimal    bool   `json:"IsOptimal"`
	Explanation  string `json:"Explanation"`
}

func renderTaxTable(r taxResponse) {
	header := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39"))
	optimal := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("82"))
	muted := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	badge := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("220")).
		Background(lipgloss.Color("22")).Padding(0, 1)
	warn := lipgloss.NewStyle().Foreground(lipgloss.Color("214"))

	vehicleLabel := "Vehículo de ocasión"
	if r.IsNewVehicle {
		vehicleLabel = warn.Render("⚠  Vehículo NUEVO (Art. 2(2)(b) Dir. IVA) — régimen especial")
	}
	fmt.Printf("\n%s  %s → %s    Precio: %s    %s\n",
		header.Render("OPTIMIZADOR IVA TRANSFRONTERIZO"),
		r.FromCountry, r.ToCountry,
		formatEUR(r.VehiclePrice),
		muted.Render(vehicleLabel),
	)

	if len(r.VIESStatus) > 0 {
		fmt.Printf("%s  ", muted.Render("VIES:"))
		for id, valid := range r.VIESStatus {
			icon := "✗"
			if valid {
				icon = "✓"
			}
			fmt.Printf("%s %s  ", icon, id)
		}
		fmt.Println()
	}

	fmt.Println(strings.Repeat("─", 90))
	fmt.Printf("  %-3s  %-30s  %-8s  %-12s  %-14s  %-12s\n",
		"#", "Régimen", "Tipo VAT", "Base impon.", "IVA irrecup.", "Coste total")
	fmt.Println(strings.Repeat("─", 90))

	for i, route := range r.Routes {
		regime := taxRegimeName(route.Route.Regime)
		vatPct := fmt.Sprintf("%.1f%%", route.Route.VATRate*100)
		taxBase := formatEUR(route.TaxableBase)
		vatAmt := formatEUR(route.VATAmount)
		totalCost := formatEUR(route.TotalCost)

		row := fmt.Sprintf("  %-3s  %-30s  %-8s  %-12s  %-14s  %-12s",
			fmt.Sprintf("%d", i+1), regime, vatPct,
			taxBase, vatAmt, totalCost,
		)

		if route.IsOptimal {
			fmt.Printf("%s  %s\n", optimal.Render(row), badge.Render("ÓPTIMO"))
		} else {
			fmt.Println(muted.Render(row))
		}
	}

	fmt.Println(strings.Repeat("─", 90))

	if r.OptimalRoute != nil && len(r.Routes) > 1 {
		worst := r.Routes[len(r.Routes)-1]
		saving := worst.VATAmount - r.OptimalRoute.VATAmount
		fmt.Printf("\n  %s %s en IVA irrecuperable vs ruta menos favorable (%s)\n",
			optimal.Render("Ahorro óptimo:"),
			optimal.Render(formatEUR(saving)),
			taxRegimeName(worst.Route.Regime),
		)
	}

	if r.OptimalRoute != nil {
		fmt.Printf("\n  %s\n  %s\n",
			header.Render("Cálculo ruta óptima:"),
			wordWrap(r.OptimalRoute.Explanation, 85),
		)
		fmt.Printf("\n  %s\n  %s\n",
			muted.Render("Base legal:"),
			muted.Render(wordWrap(r.OptimalRoute.Route.LegalBasis, 85)),
		)
	}
	fmt.Println()
}

func taxRegimeName(r string) string {
	switch r {
	case "INTRA_COMMUNITY":
		return "Adquisición intracomunitaria"
	case "MARGIN_SCHEME":
		return "Régimen de margen"
	case "EXPORT_IMPORT":
		return "Exportación/Importación"
	default:
		return r
	}
}

func formatEUR(cents int64) string {
	eur := float64(cents) / 100
	s := strconv.FormatFloat(eur, 'f', 2, 64)
	parts := strings.Split(s, ".")
	intPart := parts[0]
	neg := ""
	if strings.HasPrefix(intPart, "-") {
		neg = "-"
		intPart = intPart[1:]
	}
	var result []byte
	for i, c := range intPart {
		if i > 0 && (len(intPart)-i)%3 == 0 {
			result = append(result, '.')
		}
		result = append(result, byte(c))
	}
	return "€" + neg + string(result) + "," + parts[1]
}

func wordWrap(s string, width int) string {
	if len(s) <= width {
		return s
	}
	var lines []string
	for len(s) > width {
		cut := width
		for cut > 0 && s[cut] != ' ' {
			cut--
		}
		if cut == 0 {
			cut = width
		}
		lines = append(lines, s[:cut])
		s = "  " + strings.TrimSpace(s[cut:])
	}
	lines = append(lines, s)
	return strings.Join(lines, "\n  ")
}

func getEnvOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
