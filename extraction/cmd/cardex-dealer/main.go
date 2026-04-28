// cardex-dealer — CLI for managing Edge Push dealer accounts.
//
// Usage:
//
//	cardex dealer register --name "AutoHaus Berlin" --country DE --vat DE123456789
//	cardex dealer list
//	cardex dealer revoke <dealer_id>
//
// The CLI reads EDGE_DB_PATH for the SQLite database path.
// Default: ./data/discovery.db
//
// # Output
//
// register: prints dealer_id and api_key to stdout.
//   KEEP THE API KEY SAFE — it is shown only once.
//
// list: tab-separated table of all dealers (active + revoked).
//
// revoke: marks the dealer as revoked (no confirmation prompt).
//
// # VIES integration
//
// When --vies flag is set (default: true for EU countries), the VAT number is
// validated against the VIES REST API before registration.
// CH dealers use the UID-Register; validation is deferred (flag ignored for CH).
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"strings"
	"text/tabwriter"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/extraction/internal/extractor/e12_edge/server"
)

const defaultDBPath = "./data/discovery.db"

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	dbPath := os.Getenv("EDGE_DB_PATH")
	if dbPath == "" {
		dbPath = defaultDBPath
	}

	switch os.Args[1] {
	case "register":
		cmdRegister(dbPath, os.Args[2:])
	case "list":
		cmdList(dbPath)
	case "revoke":
		cmdRevoke(dbPath, os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n", os.Args[1])
		usage()
		os.Exit(1)
	}
}

// ─── register ────────────────────────────────────────────────────────────────

func cmdRegister(dbPath string, args []string) {
	fs := flag.NewFlagSet("register", flag.ExitOnError)
	name := fs.String("name", "", "Dealer display name (required)")
	country := fs.String("country", "", "ISO-3166-1 alpha-2 country code, e.g. DE (required)")
	vat := fs.String("vat", "", "VAT number, e.g. DE123456789 (required)")
	skipVIES := fs.Bool("skip-vies", false, "Skip VIES VAT validation (not recommended for production)")
	fs.Parse(args) //nolint:errcheck

	if *name == "" || *country == "" || *vat == "" {
		fmt.Fprintln(os.Stderr, "Error: --name, --country, and --vat are required")
		fs.Usage()
		os.Exit(1)
	}

	*country = strings.ToUpper(*country)

	// VIES validation for EU countries (skip for CH / non-EU).
	viesVerified := false
	if !*skipVIES && *country != "CH" {
		var viesErr error
		viesVerified, viesErr = verifyVIES(*country, *vat)
		if viesErr != nil {
			fmt.Fprintf(os.Stderr, "Warning: VIES validation failed: %v (proceeding with vies_verified=false)\n", viesErr)
		} else if !viesVerified {
			fmt.Fprintln(os.Stderr, "Warning: VIES returned isValid=false for this VAT number")
			fmt.Fprintln(os.Stderr, "Proceeding with vies_verified=false — dealer registered but flagged")
		}
	}

	db, err := openDB(dbPath)
	if err != nil {
		fatal(err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	dealerID, apiKey, err := db.RegisterDealer(ctx, *name, *country, *vat, viesVerified)
	if err != nil {
		fatal(fmt.Errorf("register: %w", err))
	}

	fmt.Println("Dealer registered successfully.")
	fmt.Println()
	fmt.Printf("  dealer_id  : %s\n", dealerID)
	fmt.Printf("  api_key    : %s\n", apiKey)
	fmt.Printf("  country    : %s\n", *country)
	fmt.Printf("  vat_number : %s\n", *vat)
	fmt.Printf("  vies       : %v\n", viesVerified)
	fmt.Println()
	fmt.Println("IMPORTANT: The api_key is shown only once. Store it securely.")
	fmt.Println("           Provide dealer_id + api_key to the Tauri client.")
}

// ─── list ─────────────────────────────────────────────────────────────────────

func cmdList(dbPath string) {
	db, err := openDB(dbPath)
	if err != nil {
		fatal(err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := db.ListDealers(ctx)
	if err != nil {
		fatal(fmt.Errorf("list: %w", err))
	}

	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "DEALER_ID\tNAME\tCOUNTRY\tVAT\tVIES\tACTIVE\tCREATED_AT")
	for _, r := range rows {
		vies := "no"
		if r.VIESVerified == 1 {
			vies = "yes"
		}
		active := "yes"
		if !r.Active {
			active = "REVOKED"
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
			r.DealerID, r.Name, r.Country, r.VATNumber, vies, active, r.CreatedAt)
	}
	w.Flush()
	if len(rows) == 0 {
		fmt.Println("(no dealers registered)")
	}
}

// ─── revoke ──────────────────────────────────────────────────────────────────

func cmdRevoke(dbPath string, args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "Usage: cardex-dealer revoke <dealer_id>")
		os.Exit(1)
	}
	dealerID := args[0]

	db, err := openDB(dbPath)
	if err != nil {
		fatal(err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := db.RevokeDealer(ctx, dealerID); err != nil {
		fatal(fmt.Errorf("revoke %s: %w", dealerID, err))
	}

	fmt.Printf("Dealer %s revoked. The api_key is now invalid.\n", dealerID)
}

// ─── VIES validation ─────────────────────────────────────────────────────────

type viesResponse struct {
	IsValid bool `json:"isValid"`
}

// verifyVIES calls the VIES REST API to validate a VAT number.
// Returns (true, nil) if the VAT number is valid, (false, nil) if invalid,
// or (false, err) if the API call fails.
func verifyVIES(countryCode, vatNumber string) (bool, error) {
	// Strip country prefix if present (e.g. "DE" from "DE123456789").
	vatStripped := strings.TrimPrefix(vatNumber, countryCode)

	url := fmt.Sprintf(
		"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/%s/vat/%s",
		countryCode, vatStripped,
	)

	client := &http.Client{
		Timeout: 15 * time.Second,
	}

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	req.Header.Set("User-Agent", "CardexBot/1.0")
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return false, fmt.Errorf("VIES API: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("VIES API: HTTP %d", resp.StatusCode)
	}

	var result viesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("VIES API: parse: %w", err)
	}

	return result.IsValid, nil
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func openDB(dbPath string) (*server.DB, error) {
	db, err := server.NewDB(dbPath)
	if err != nil {
		return nil, fmt.Errorf("open DB %q: %w", dbPath, err)
	}
	return db, nil
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "Error:", err)
	os.Exit(1)
}

func usage() {
	fmt.Fprintln(os.Stderr, `Usage: cardex-dealer <command> [flags]

Commands:
  register  --name <name> --country <CC> --vat <VAT>   Register a new dealer
  list                                                  List all dealers
  revoke    <dealer_id>                                 Revoke a dealer's access

Environment:
  EDGE_DB_PATH   Path to the SQLite database (default: ./data/discovery.db)

Examples:
  cardex-dealer register --name "AutoHaus Berlin" --country DE --vat DE123456789
  cardex-dealer list
  cardex-dealer revoke 01JFXYZABCDE1234567`)
}
