package check

// CH plate resolver — Switzerland
//
// Swiss plates have the format: [CANTON][NUMBER], e.g. "ZH 123456" → normalised "ZH123456".
// The canton abbreviation is 1-4 letters, followed by 1-6 digits.
//
// Investigation of all 26 cantons (+ special plates):
//
//  FREE online lookup (5 cantons — Strassenverkehrsamt portal with public form):
//  ┌─────┬──────────────────────────────────────────────────────────────────────────┐
//  │ ZH  │ Motorfahrzeugkontrolle Zürich — mfk.zh.ch                               │
//  │     │ GET /internet/sicherheitsdirektion/mfk/de/fahrzeugpruefung/             │
//  │     │     halteranfrage.html  (JSF form — returns make/type, NOT VIN)          │
//  ├─────┼──────────────────────────────────────────────────────────────────────────┤
//  │ AG  │ Motorfahrzeugkontrolle Aargau — mfk.ag.ch                               │
//  │     │ Similar portal — returns basic vehicle type, NOT VIN                     │
//  ├─────┼──────────────────────────────────────────────────────────────────────────┤
//  │ LU  │ Motorfahrzeugkontrolle Luzern — mfk.lu.ch                               │
//  │     │ Similar portal                                                           │
//  ├─────┼──────────────────────────────────────────────────────────────────────────┤
//  │ SH  │ Motorfahrzeugkontrolle Schaffhausen — strassenverkehr.sh.ch             │
//  │     │ Similar portal                                                           │
//  ├─────┼──────────────────────────────────────────────────────────────────────────┤
//  │ ZG  │ Motorfahrzeugkontrolle Zug — mfk.zg.ch                                 │
//  │     │ Similar portal                                                           │
//  └─────┴──────────────────────────────────────────────────────────────────────────┘
//
//  eAutoindex (paid — CHF 1.00/query) — operated by ASA Suisse (auto-suisse.ch):
//  BE, BL, BS, FR, GE, GR, JU, NE, NW, OW, SG, SO, TG, VD, VS, AR, AI
//
//  Own portals (investigated individually):
//  ┌─────┬──────────────────────────────────────────────────────────────────────────┐
//  │ GL  │ Kanton Glarus MFK — gl.ch/mfk — no public online plate lookup           │
//  │ SZ  │ Kanton Schwyz MFK — sz.ch — no public online plate lookup               │
//  │ UR  │ Kanton Uri MFK — ur.ch — no public online plate lookup                  │
//  │ TI  │ Cantone Ticino — ti.ch — Italian portal; no public plate lookup         │
//  │ AI  │ Kanton Appenzell Innerrhoden — very small; uses eAutoindex               │
//  │ AR  │ Kanton Appenzell Ausserrhoden — uses eAutoindex                          │
//  └─────┴──────────────────────────────────────────────────────────────────────────┘
//
//  Special plates (not cantonal):
//  CD = Diplomatic Corps, CC = Consular Corps, A = Army, M = Military, P = Police
//  → These plates cannot be looked up in any public registry.
//
// VIN availability: Swiss MFK portals return Halteranfrage (holder query) data:
// make, vehicle type, and validity — NOT VIN. VIN is protected by Swiss data law.
//
// What this resolver does:
//   1. Extracts the canton from the plate prefix.
//   2. For ZH/AG/LU/SH/ZG: attempts to scrape the free cantonal MFK portal.
//      Returns: make, model (vehicle type), registration validity.
//   3. For eAutoindex cantons: returns ErrPlateResolutionUnavailable with message
//      "uses eAutoindex (CHF 1.00/query — autos-suisse.ch)".
//   4. For others: returns ErrPlateResolutionUnavailable with per-canton explanation.

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type chPlateResolver struct {
	client *http.Client
}

func newCHPlateResolver(client *http.Client) *chPlateResolver {
	return &chPlateResolver{client: client}
}

// validateCHPlate ensures the plate has a plausible Swiss format.
// Swiss plates: canton prefix (2 chars) + 1-6 digits, e.g. "ZH123456" (normalised).
func validateCHPlate(plate string) error {
	if len(plate) < 3 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid CH plate length %d", ErrPlateNotFound, len(plate))
	}
	// Must start with letters and end with digits.
	hasLetters := false
	hasDigits := false
	for _, r := range plate {
		switch {
		case r >= 'A' && r <= 'Z':
			hasLetters = true
		case r >= '0' && r <= '9':
			hasDigits = true
		default:
			return fmt.Errorf("%w: invalid character in CH plate", ErrPlateNotFound)
		}
	}
	if !hasLetters || !hasDigits {
		return fmt.Errorf("%w: CH plate must contain both letters and digits", ErrPlateNotFound)
	}
	return nil
}

func (r *chPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateCHPlate(plate); err != nil {
		return nil, err
	}

	canton, number := chExtractCanton(plate)
	if canton == "" {
		return nil, fmt.Errorf("%w: cannot extract canton from CH plate %q", ErrPlateResolutionUnavailable, plate)
	}

	switch canton {
	// ── Free cantonal portals ─────────────────────────────────────────────────
	case "ZH":
		return r.resolveZH(ctx, canton, number, plate)
	case "AG":
		return r.resolveAG(ctx, canton, number, plate)
	case "LU":
		return r.resolveLU(ctx, canton, number, plate)
	case "SH":
		return r.resolveSH(ctx, canton, number, plate)
	case "ZG":
		return r.resolveZG(ctx, canton, number, plate)

	// ── eAutoindex (paid CHF 1.00/query) ─────────────────────────────────────
	case "BE", "BL", "BS", "FR", "GE", "GR", "JU", "NE", "NW", "OW", "SG", "SO", "TG", "VD", "VS", "AR", "AI":
		return nil, fmt.Errorf(
			"%w: CH/%s uses eAutoindex (CHF 1.00/query via auto-suisse.ch). "+
				"No free public lookup available for this canton.",
			ErrPlateResolutionUnavailable, canton,
		)

	// ── Cantons with no public lookup ─────────────────────────────────────────
	case "GL":
		return nil, fmt.Errorf("%w: CH/GL (Kanton Glarus) — MFK portal (gl.ch/mfk) has no public online plate lookup", ErrPlateResolutionUnavailable)
	case "SZ":
		return nil, fmt.Errorf("%w: CH/SZ (Kanton Schwyz) — MFK portal (sz.ch) has no public online plate lookup", ErrPlateResolutionUnavailable)
	case "UR":
		return nil, fmt.Errorf("%w: CH/UR (Kanton Uri) — MFK portal (ur.ch) has no public online plate lookup", ErrPlateResolutionUnavailable)
	case "TI":
		return nil, fmt.Errorf("%w: CH/TI (Cantone Ticino) — portale ti.ch has no public plate lookup", ErrPlateResolutionUnavailable)

	// ── Special plates ────────────────────────────────────────────────────────
	case "CD", "CC":
		return nil, fmt.Errorf("%w: CH/%s is a diplomatic/consular plate — not in any public registry", ErrPlateResolutionUnavailable, canton)
	case "A", "M", "P":
		return nil, fmt.Errorf("%w: CH/%s is a military/police plate — not in any public registry", ErrPlateResolutionUnavailable, canton)

	default:
		return nil, fmt.Errorf("%w: unknown CH canton prefix %q", ErrPlateResolutionUnavailable, canton)
	}
}

// chExtractCanton extracts the canton abbreviation (letters) and number (digits)
// from a normalised Swiss plate like "ZH123456" → ("ZH", "123456").
func chExtractCanton(plate string) (string, string) {
	i := 0
	for i < len(plate) && plate[i] >= 'A' && plate[i] <= 'Z' {
		i++
	}
	if i == 0 || i == len(plate) {
		return "", ""
	}
	return plate[:i], plate[i:]
}

// ── Zürich (ZH) ──────────────────────────────────────────────────────────────
//
// Portal: motorfahrzeugkontrolle.zh.ch
// The MFK Zürich Halteranfrage form accepts a plate number and returns:
//   - Fahrzeugart (vehicle type / make+type string)
//   - Gültig bis (valid until — next MFK date)
// VIN is NOT returned (protected by cantonal data law).

func (r *chPlateResolver) resolveZH(ctx context.Context, canton, number, plate string) (*PlateResult, error) {
	const baseURL = "https://www.motorfahrzeugkontrolle.zh.ch/internet/sicherheitsdirektion/mfk/de/fahrzeugpruefung/halteranfrage.html"

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  "Kanton Zürich",
		Source:    "Motorfahrzeugkontrolle Zürich (mfk.zh.ch) — Halteranfrage",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	body, err := r.scrapeChForm(ctx, baseURL, map[string]string{
		"kantonalKennzeichen": number,
		"kanton":              "ZH",
		"kennzeichen":         number,
	})
	if err != nil {
		return nil, fmt.Errorf("%w: ZH portal: %v", ErrPlateResolutionUnavailable, err)
	}

	r.parseChMFKResponse(body, result)
	if result.Make == "" && result.NextInspectionDate == nil {
		return nil, fmt.Errorf("%w: ZH portal returned no vehicle data for plate %s", ErrPlateNotFound, plate)
	}
	return result, nil
}

// ── Aargau (AG) ───────────────────────────────────────────────────────────────

func (r *chPlateResolver) resolveAG(ctx context.Context, canton, number, plate string) (*PlateResult, error) {
	const baseURL = "https://www.mfk.ag.ch/fahrzeugkontrolle/halteranfrage"

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  "Kanton Aargau",
		Source:    "Motorfahrzeugkontrolle Aargau (mfk.ag.ch) — Halteranfrage",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	body, err := r.scrapeChForm(ctx, baseURL, map[string]string{
		"kennzeichen": number,
		"kanton":      "AG",
	})
	if err != nil {
		return nil, fmt.Errorf("%w: AG portal: %v", ErrPlateResolutionUnavailable, err)
	}

	r.parseChMFKResponse(body, result)
	if result.Make == "" && result.NextInspectionDate == nil {
		return nil, fmt.Errorf("%w: AG portal returned no vehicle data for plate %s", ErrPlateNotFound, plate)
	}
	return result, nil
}

// ── Luzern (LU) ───────────────────────────────────────────────────────────────

func (r *chPlateResolver) resolveLU(ctx context.Context, canton, number, plate string) (*PlateResult, error) {
	const baseURL = "https://www.mfk.lu.ch/fahrzeugkontrolle/halteranfrage"

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  "Kanton Luzern",
		Source:    "Motorfahrzeugkontrolle Luzern (mfk.lu.ch) — Halteranfrage",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	body, err := r.scrapeChForm(ctx, baseURL, map[string]string{
		"kennzeichen": number,
		"kanton":      "LU",
	})
	if err != nil {
		return nil, fmt.Errorf("%w: LU portal: %v", ErrPlateResolutionUnavailable, err)
	}

	r.parseChMFKResponse(body, result)
	if result.Make == "" && result.NextInspectionDate == nil {
		return nil, fmt.Errorf("%w: LU portal returned no vehicle data for plate %s", ErrPlateNotFound, plate)
	}
	return result, nil
}

// ── Schaffhausen (SH) ─────────────────────────────────────────────────────────

func (r *chPlateResolver) resolveSH(ctx context.Context, canton, number, plate string) (*PlateResult, error) {
	const baseURL = "https://www.strassenverkehrsamt.sh.ch/fahrzeuge/halteranfrage"

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  "Kanton Schaffhausen",
		Source:    "Strassenverkehrsamt Schaffhausen (sh.ch) — Halteranfrage",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	body, err := r.scrapeChForm(ctx, baseURL, map[string]string{
		"kennzeichen": number,
		"kanton":      "SH",
	})
	if err != nil {
		return nil, fmt.Errorf("%w: SH portal: %v", ErrPlateResolutionUnavailable, err)
	}

	r.parseChMFKResponse(body, result)
	if result.Make == "" && result.NextInspectionDate == nil {
		return nil, fmt.Errorf("%w: SH portal returned no vehicle data for plate %s", ErrPlateNotFound, plate)
	}
	return result, nil
}

// ── Zug (ZG) ─────────────────────────────────────────────────────────────────

func (r *chPlateResolver) resolveZG(ctx context.Context, canton, number, plate string) (*PlateResult, error) {
	const baseURL = "https://www.mfk.zg.ch/fahrzeuge/halteranfrage"

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  "Kanton Zug",
		Source:    "Motorfahrzeugkontrolle Zug (mfk.zg.ch) — Halteranfrage",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	body, err := r.scrapeChForm(ctx, baseURL, map[string]string{
		"kennzeichen": number,
		"kanton":      "ZG",
	})
	if err != nil {
		return nil, fmt.Errorf("%w: ZG portal: %v", ErrPlateResolutionUnavailable, err)
	}

	r.parseChMFKResponse(body, result)
	if result.Make == "" && result.NextInspectionDate == nil {
		return nil, fmt.Errorf("%w: ZG portal returned no vehicle data for plate %s", ErrPlateNotFound, plate)
	}
	return result, nil
}

// ── shared CH scraping helpers ────────────────────────────────────────────────

// scrapeChForm sends a GET to baseURL, extracts hidden form fields, then POSTs
// with the combined field set. Returns the response body.
func (r *chPlateResolver) scrapeChForm(ctx context.Context, baseURL string, fields map[string]string) (string, error) {
	// GET the form page to collect any hidden / CSRF fields.
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "de-CH,de;q=0.9,fr;q=0.8,en;q=0.7")

	resp, err := r.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("GET form: %w", err)
	}
	defer resp.Body.Close()
	getBody, _ := io.ReadAll(io.LimitReader(resp.Body, 128*1024))

	// Build POST form.
	formData := url.Values{}
	extractHiddenFields(string(getBody), formData)
	for k, v := range fields {
		formData.Set(k, v)
	}

	postReq, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL, strings.NewReader(formData.Encode()))
	if err != nil {
		return "", err
	}
	postReq.Header.Set("User-Agent", plateUA)
	postReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	postReq.Header.Set("Referer", baseURL)
	postReq.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

	postResp, err := r.client.Do(postReq)
	if err != nil {
		return "", fmt.Errorf("POST form: %w", err)
	}
	defer postResp.Body.Close()

	if postResp.StatusCode == http.StatusNotFound || postResp.StatusCode == http.StatusForbidden {
		return "", fmt.Errorf("portal HTTP %d", postResp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(postResp.Body, 256*1024))
	if err != nil {
		return "", fmt.Errorf("read response: %w", err)
	}
	return string(body), nil
}

// parseChMFKResponse extracts vehicle info from a Swiss cantonal MFK HTML response.
// MFK portals typically return a simple table with:
//   - Marke / Typ (make / type)
//   - Gültig bis / Nächste Prüfung (next inspection date)
func (r *chPlateResolver) parseChMFKResponse(body string, result *PlateResult) {
	upper := strings.ToUpper(body)

	// Make / Typ — various label variants used by different cantons.
	for _, label := range []string{"MARKE", "FAHRZEUGTYP", "TYP", "FAHRZEUG"} {
		if v := htmlExtractAfter(body, label, "<td", "</td>"); v != "" {
			clean := stripHTMLTags(v)
			if clean != "" && result.Make == "" {
				// Some portals return "MARKE / TYP" as a combined string.
				parts := strings.SplitN(clean, "/", 2)
				result.Make = strings.TrimSpace(parts[0])
				if len(parts) > 1 {
					result.Model = strings.TrimSpace(parts[1])
				}
			}
			break
		}
	}
	// Fallback: try after German header cell.
	if result.Make == "" {
		if v := htmlExtractAfter(upper, ">MARKE<", "<TD", "</TD>"); v != "" {
			result.Make = stripHTMLTags(v)
		}
	}

	// Next inspection / validity date.
	for _, label := range []string{"Gültig bis", "Nächste Prüfung", "Prüfungsdatum", "GULTIG"} {
		if d := extractDateAfterMarker(upper, strings.ToUpper(label)); !d.IsZero() {
			result.NextInspectionDate = &d
			result.LastInspectionResult = "pass"
			break
		}
	}
}
