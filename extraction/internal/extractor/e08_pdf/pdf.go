// Package e08_pdf implements extraction strategy E08 — PDF Catalog Parsing.
//
// # Strategy
//
// Some dealers publish periodic vehicle catalogs as PDF files, accessible from
// their homepage or at well-known paths (e.g. /catalogue.pdf, /inventory.pdf).
// E08 discovers such PDFs via homepage link crawling and path probing, extracts
// text from each page using github.com/ledongthuc/pdf (pure-Go, no CGO), then
// applies a heuristic tabular parser to map rows to vehicle records.
//
// # Text extraction approach
//
// Each PDF page is converted to plain text; lines are split and tokenized.
// A header-detection pass looks for row-0 keywords (VIN, Make, Model, Year,
// Price) to learn column order. Subsequent rows are mapped accordingly.
// If no explicit header is found, the fallback heuristic looks for year-like
// numbers and known automotive makes.
//
// # OCR for scanned PDFs
//
// PDFs that are scanned images yield no text from the parser. Tesseract OCR
// support is deferred to a follow-up sprint; such PDFs are silently skipped.
//
// Priority: 700 (same tier as E09 Excel/CSV).
package e08_pdf

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/ledongthuc/pdf"

	"cardex.eu/extraction/internal/normalize"
	"cardex.eu/extraction/internal/pipeline"
)

const (
	strategyID   = "E08"
	strategyName = "PDF Catalog"
	maxPDFBytes  = 32 << 20 // 32 MiB
	maxPages     = 50       // skip very long PDFs
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// pdfProbePaths are the candidate paths probed for PDF catalogs.
var pdfProbePaths = []string{
	"/catalog.pdf",
	"/catalogue.pdf",
	"/inventory.pdf",
	"/inventaire.pdf",
	"/catalogo.pdf",
	"/fahrzeugliste.pdf",
	"/fahrzeuge.pdf",
	"/voitures.pdf",
	"/inventory-list.pdf",
	"/vehicle-list.pdf",
}

// pdfLinkKeywords are the search terms used when scanning homepage links for PDFs.
var pdfLinkKeywords = []string{
	"catalog", "catalogue", "inventory", "inventaire", "fahrzeug",
	"voiture", "coche", "auto", "listing", "stock",
}

// reYear matches a 4-digit model year.
var reYear = regexp.MustCompile(`\b(19[89]\d|20[012]\d)\b`)

// PDF is the E08 extraction strategy.
type PDF struct {
	client      *http.Client
	rateLimitMs int
	log         *slog.Logger
}

// New constructs a PDF strategy with default HTTP client.
func New() *PDF {
	return NewWithClient(&http.Client{Timeout: 30 * time.Second}, 1000)
}

// NewWithClient constructs a PDF strategy with custom client and rate limit.
func NewWithClient(c *http.Client, rateLimitMs int) *PDF {
	return &PDF{
		client:      c,
		rateLimitMs: rateLimitMs,
		log:         slog.Default().With("strategy", strategyID),
	}
}

func (e *PDF) ID() string    { return strategyID }
func (e *PDF) Name() string  { return strategyName }
func (e *PDF) Priority() int { return pipeline.PriorityE08 }

// Applicable returns true for all dealers — any site may publish a PDF catalog.
func (e *PDF) Applicable(_ pipeline.Dealer) bool { return true }

// Extract discovers PDF catalogs via homepage links and probe paths, then
// extracts vehicle records from the PDF text.
func (e *PDF) Extract(ctx context.Context, dealer pipeline.Dealer) (*pipeline.ExtractionResult, error) {
	result := &pipeline.ExtractionResult{
		DealerID:    dealer.ID,
		Strategy:    strategyID,
		ExtractedAt: time.Now(),
	}

	baseURL := dealer.URLRoot
	if baseURL == "" {
		baseURL = "https://" + dealer.Domain
	}

	// 1. Discover PDF URLs.
	pdfURLs := e.discoverPDFs(ctx, baseURL)
	if len(pdfURLs) == 0 {
		result.Errors = append(result.Errors, pipeline.ExtractionError{
			Code:    "NO_PDF",
			Message: "no PDF catalog found via homepage links or probe paths",
			URL:     baseURL,
		})
		return result, nil
	}

	seenVehicles := map[string]bool{}

	// 2. Process each PDF.
	for i, pdfURL := range pdfURLs {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			sleep := e.rateLimitMs
			if sleep <= 0 {
				sleep = 50
			}
			select {
			case <-ctx.Done():
				return result, nil
			case <-time.After(time.Duration(sleep) * time.Millisecond):
			}
		}

		vehicles, err := e.fetchAndParse(ctx, pdfURL)
		if err != nil {
			result.Errors = append(result.Errors, pipeline.ExtractionError{
				Code:    "PDF_ERROR",
				Message: err.Error(),
				URL:     pdfURL,
			})
			continue
		}

		result.SourceURL = pdfURL
		result.SourceCount++

		for _, v := range vehicles {
			key := vehicleKey(v)
			if !seenVehicles[key] {
				seenVehicles[key] = true
				result.Vehicles = append(result.Vehicles, v)
			}
		}

		if len(result.Vehicles) > 0 {
			break // first successful PDF is enough
		}
	}

	return result, nil
}

// discoverPDFs finds PDF catalog URLs from the homepage and common paths.
func (e *PDF) discoverPDFs(ctx context.Context, baseURL string) []string {
	var urls []string

	// 1. Scan homepage for PDF links.
	homeLinks := e.scanHomepageLinks(ctx, baseURL)
	urls = append(urls, homeLinks...)

	if len(urls) > 0 {
		return urls
	}

	// 2. Probe common paths.
	for _, path := range pdfProbePaths {
		if ctx.Err() != nil {
			break
		}
		u := baseURL + path
		if e.probeURL(ctx, u) {
			urls = append(urls, u)
			break
		}
	}
	return urls
}

// scanHomepageLinks fetches the homepage and finds PDF links with vehicle keywords.
func (e *PDF) scanHomepageLinks(ctx context.Context, baseURL string) []string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := e.client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return nil
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(body)))
	if err != nil {
		return nil
	}

	var pdfURLs []string
	doc.Find("a[href]").Each(func(_ int, s *goquery.Selection) {
		href, _ := s.Attr("href")
		if !strings.HasSuffix(strings.ToLower(href), ".pdf") {
			return
		}
		linkText := strings.ToLower(s.Text() + " " + href)
		for _, kw := range pdfLinkKeywords {
			if strings.Contains(linkText, kw) {
				abs := normalize.CanonicalizePhotoURL(href, baseURL)
				pdfURLs = append(pdfURLs, abs)
				return
			}
		}
	})
	return pdfURLs
}

// probeURL returns true if a HEAD request to u returns HTTP 200.
func (e *PDF) probeURL(ctx context.Context, u string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, u, nil)
	if err != nil {
		return false
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := e.client.Do(req)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// fetchAndParse downloads a PDF and extracts vehicle records from its text.
func (e *PDF) fetchAndParse(ctx context.Context, u string) ([]*pipeline.VehicleRaw, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/pdf,*/*")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("HTTP 429: %s", u)
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, u)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxPDFBytes))
	if err != nil {
		return nil, fmt.Errorf("read PDF body: %w", err)
	}

	return parsePDFBytes(body)
}

// parsePDFBytes extracts text from a PDF byte slice and parses vehicle records.
func parsePDFBytes(data []byte) ([]*pipeline.VehicleRaw, error) {
	r, err := pdf.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("pdf.NewReader: %w", err)
	}

	var allText strings.Builder
	numPages := r.NumPage()
	if numPages > maxPages {
		numPages = maxPages
	}

	for i := 1; i <= numPages; i++ {
		page := r.Page(i)
		if page.V.IsNull() {
			continue
		}
		text, err := page.GetPlainText(nil)
		if err != nil {
			continue // non-fatal — scanned page
		}
		allText.WriteString(text)
		allText.WriteString("\n")
	}

	return parseVehicleText(allText.String()), nil
}

// parseVehicleText applies heuristic parsing to PDF-extracted plain text.
//
// Two passes:
//  1. Header detection: looks for a row containing VIN/Make/Model/Year/Price.
//  2. Data rows: maps each subsequent non-empty line to a VehicleRaw.
//
// Falls back to line-by-line heuristic if no header row is found.
func parseVehicleText(text string) []*pipeline.VehicleRaw {
	lines := splitLines(text)
	if len(lines) == 0 {
		return nil
	}

	// Try header detection.
	headerIdx, colMap := detectTableHeader(lines)
	if headerIdx >= 0 && len(colMap) >= 2 {
		return parseTableRows(lines[headerIdx+1:], colMap)
	}

	// Fallback: scan each line for vehicle-like content.
	return parseHeuristicLines(lines)
}

// splitLines splits text into non-empty trimmed lines.
func splitLines(text string) []string {
	var lines []string
	for _, l := range strings.Split(text, "\n") {
		if t := strings.TrimSpace(l); t != "" {
			lines = append(lines, t)
		}
	}
	return lines
}

// Column index constants for header detection.
const (
	colVIN   = "vin"
	colMake  = "make"
	colModel = "model"
	colYear  = "year"
	colPrice = "price"
)

// detectTableHeader scans lines for a header row containing vehicle field names.
// Returns the line index and a column-name → token-index map.
func detectTableHeader(lines []string) (int, map[string]int) {
	headerAliases := map[string][]string{
		colVIN:   {"vin", "chassis", "serial"},
		colMake:  {"make", "brand", "marque", "marke", "marca"},
		colModel: {"model", "modele", "modell", "modelo"},
		colYear:  {"year", "annee", "baujahr", "ano", "yr"},
		colPrice: {"price", "prix", "preis", "precio", "cost"},
	}

	for lineIdx, line := range lines {
		tokens := tokenizeLine(line)
		if len(tokens) < 2 {
			continue
		}
		colMap := map[string]int{}
		for tokIdx, tok := range tokens {
			lower := strings.ToLower(tok)
			for colName, aliases := range headerAliases {
				for _, alias := range aliases {
					if strings.Contains(lower, alias) {
						if _, already := colMap[colName]; !already {
							colMap[colName] = tokIdx
						}
					}
				}
			}
		}
		if len(colMap) >= 2 {
			return lineIdx, colMap
		}
	}
	return -1, nil
}

// parseTableRows maps data rows to VehicleRaw records using the detected column map.
func parseTableRows(lines []string, colMap map[string]int) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw
	for _, line := range lines {
		tokens := tokenizeLine(line)
		if len(tokens) == 0 {
			continue
		}
		v := &pipeline.VehicleRaw{}
		if idx, ok := colMap[colVIN]; ok && idx < len(tokens) {
			if vin := normalize.NormalizeVIN(tokens[idx]); vin != "" {
				v.VIN = &vin
			}
		}
		if idx, ok := colMap[colMake]; ok && idx < len(tokens) {
			mk := normalize.NormalizeMake(tokens[idx])
			v.Make = &mk
		}
		if idx, ok := colMap[colModel]; ok && idx < len(tokens) {
			v.Model = &tokens[idx]
		}
		if idx, ok := colMap[colYear]; ok && idx < len(tokens) {
			if yr, err := strconv.Atoi(tokens[idx]); err == nil && yr > 1900 {
				v.Year = &yr
			}
		}
		if idx, ok := colMap[colPrice]; ok && idx < len(tokens) {
			if p := parsePrice(tokens[idx]); p > 0 {
				v.PriceGross = &p
			}
		}
		if v.Make == nil && v.VIN == nil {
			continue
		}
		vehicles = append(vehicles, v)
	}
	return vehicles
}

// parseHeuristicLines parses lines without a known column structure.
// Each line is inspected for year, make, price patterns.
func parseHeuristicLines(lines []string) []*pipeline.VehicleRaw {
	var vehicles []*pipeline.VehicleRaw
	for _, line := range lines {
		v := &pipeline.VehicleRaw{}
		if m := reYear.FindString(line); m != "" {
			yr, _ := strconv.Atoi(m)
			v.Year = &yr
		}
		detectMakeFromLine(line, v)
		if v.Make == nil && v.Year == nil {
			continue
		}
		vehicles = append(vehicles, v)
	}
	return vehicles
}

// knownMakesLower is used for make detection in heuristic line parsing.
var knownMakesLower = []string{
	"audi", "bmw", "citroen", "citroën", "dacia", "fiat", "ford",
	"honda", "hyundai", "jaguar", "jeep", "kia", "mazda", "mercedes",
	"mini", "mitsubishi", "nissan", "opel", "peugeot", "porsche",
	"renault", "seat", "skoda", "škoda", "smart", "subaru", "suzuki",
	"tesla", "toyota", "volkswagen", "volvo", "vw",
}

// detectMakeFromLine sets v.Make if a known make is found in the line.
func detectMakeFromLine(line string, v *pipeline.VehicleRaw) {
	lower := strings.ToLower(line)
	for _, mk := range knownMakesLower {
		if strings.Contains(lower, mk) {
			proper := strings.Title(mk) //nolint:staticcheck
			v.Make = &proper
			return
		}
	}
}

// tokenizeLine splits a line into whitespace-delimited tokens.
func tokenizeLine(line string) []string {
	return strings.Fields(line)
}

// parsePrice parses a price token like "28500", "28.500", "28,500".
func parsePrice(s string) float64 {
	s = strings.Map(func(r rune) rune {
		if (r >= '0' && r <= '9') || r == '.' || r == ',' {
			return r
		}
		return -1
	}, s)
	if s == "" {
		return 0
	}
	// European decimal: trailing comma
	if i := strings.LastIndex(s, ","); i >= 0 {
		s = strings.ReplaceAll(s[:i], ".", "") + "." + s[i+1:]
	}
	var p float64
	fmt.Sscanf(s, "%f", &p)
	return p
}

// vehicleKey returns a deduplication key for a VehicleRaw.
func vehicleKey(v *pipeline.VehicleRaw) string {
	if v.VIN != nil && *v.VIN != "" {
		return "vin:" + *v.VIN
	}
	if v.SourceURL != "" {
		return v.SourceURL
	}
	make_ := ""
	if v.Make != nil {
		make_ = *v.Make
	}
	model := ""
	if v.Model != nil {
		model = *v.Model
	}
	return make_ + "|" + model
}
