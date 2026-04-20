package check

// ES plate resolver — Spain
//
// Data sources (all public, unauthenticated, free):
//
// 1. comprobarmatricula.com/api/vehiculo.php — primary. Returns a rich JSON
//    record (VIN, make, model, variant, fuel, kW, cc, body, gearbox, first
//    registration, ITV date, owners, engine code, k-type). The page embeds a
//    time-salted token in <input id="_g_tk">; we harvest it then call the
//    JSON endpoint with a Referer matching the plate page.
//
// 2. sede.dgt.gob.es/…/distintivo-ambiental — canonical DGT environmental
//    badge (0 / ECO / C / B). Much more reliable than the badge field in
//    comprobarmatricula, which assigns "0" to old diesels that in fact have
//    no badge at all.
//
// Blocked / skipped (documented in ES_ENDPOINTS.md):
// - DGT "informe-vehiculo" — requires Cl@ve or digital certificate.
// - vehiculodgt.es — SPA in front of a Stripe-gated backend.
// - auto-info.gratis — Polish site, no ES coverage.
// - ITV CCAA portals — 17 regional systems, none public.

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"
)

type esPlateResolver struct {
	client  *http.Client
	cmBase  string // comprobarmatricula.com base (no trailing slash)
	dgtBase string // sede.dgt.gob.es distintivo-ambiental page base (trailing slash)
}

func newESPlateResolver(client *http.Client) *esPlateResolver {
	return &esPlateResolver{
		client:  client,
		cmBase:  "https://comprobarmatricula.com",
		dgtBase: "https://sede.dgt.gob.es/es/vehiculos/informacion-de-vehiculos/distintivo-ambiental/",
	}
}

// NewESPlateResolverWithBases creates an ES resolver with custom URL bases
// (used by tests to substitute httptest servers).
func NewESPlateResolverWithBases(cmBase, dgtBase string) *esPlateResolver {
	return &esPlateResolver{
		client:  newPlateHTTPClient(5 * time.Second),
		cmBase:  strings.TrimRight(cmBase, "/"),
		dgtBase: dgtBase,
	}
}

// validateESPlate ensures the plate has a plausible Spanish format.
// Modern format (since 2000): 4 digits + 3 consonants, e.g. "1234BCJ".
// Old format: 2-letter province code + 4 digits + 1-2 letters.
func validateESPlate(plate string) error {
	if len(plate) < 5 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid ES plate length %d", ErrPlateNotFound, len(plate))
	}
	for _, r := range plate {
		if !((r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return fmt.Errorf("%w: invalid character in ES plate", ErrPlateNotFound)
		}
	}
	return nil
}

func (r *esPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateESPlate(plate); err != nil {
		return nil, err
	}

	result := &PlateResult{
		Plate:     plate,
		Country:   "ES",
		FetchedAt: time.Now().UTC(),
	}

	// Run both sources in parallel. Partial success on one source is fine.
	var wg sync.WaitGroup
	var cmErr, dgtErr error
	var cm cmVehiculo
	var haveCM, cmLimited bool

	wg.Add(2)
	go func() {
		defer wg.Done()
		cm, haveCM, cmLimited, cmErr = r.fetchComprobarMatricula(ctx, plate)
	}()
	go func() {
		defer wg.Done()
		dgtErr = r.fetchDGTDistintivo(ctx, plate, result)
	}()
	wg.Wait()

	if haveCM {
		applyCMToResult(cm, result)
	}

	sources := make([]string, 0, 2)
	switch {
	case haveCM:
		sources = append(sources, "comprobarmatricula.com")
	case cmLimited:
		// Integration IS active but the server IP hit CM's per-IP rate limit.
		sources = append(sources, "comprobarmatricula.com (rate-limited — retry later)")
	}
	if result.EnvironmentalBadge != "" {
		sources = append(sources, "sede.dgt.gob.es (distintivo ambiental)")
	}
	result.Source = strings.Join(sources, " + ")

	// Nothing extracted at all → treat as plate not found, unless both sources
	// errored transiently, in which case bubble an upstream-unavailable error.
	if !haveCM && result.EnvironmentalBadge == "" {
		if cmErr != nil && dgtErr != nil {
			return nil, fmt.Errorf("%w: ES sources unreachable (cm: %v; dgt: %v)",
				ErrPlateResolutionUnavailable, cmErr, dgtErr)
		}
		return nil, fmt.Errorf("%w: no ES source returned data for plate %s",
			ErrPlateNotFound, plate)
	}

	// Partial when primary source missing (CM provides the meaty fields).
	result.Partial = !haveCM
	return result, nil
}

// ── comprobarmatricula.com ─────────────────────────────────────────────────────

// cmVehiculo mirrors the JSON returned by /api/vehiculo.php. All fields are
// optional — older plates occasionally lack VIN or ITV date.
type cmVehiculo struct {
	OK                 int    `json:"ok"`
	Limit              bool   `json:"limit"` // true when anti-scrape rate-limit fires
	Mat                string `json:"mat"`
	Brand              string `json:"brand"`
	MarcaOficial       string `json:"marca_oficial"`
	Model              string `json:"model"`
	ModeloCompleto     string `json:"modelo_completo"`
	Version            string `json:"version"`
	Fuel               string `json:"fuel"`
	PotenciaCV         int    `json:"potencia_cv"`
	PotenciaKW         int    `json:"potencia_kw"`
	CilindradaCC       string `json:"cilindrada_cc"` // "1968 cc"
	Carroceria         string `json:"carroceria"`
	Caja               string `json:"caja"`
	CodigoMotor        string `json:"codigo_motor"`
	VIN                string `json:"vin"`
	FechaMatriculacion string `json:"fecha_matriculacion"` // DD/MM/YYYY
	AnneeModelo        string `json:"annee_modelo"`        // "2009"
	Etiq               string `json:"etiq"`
	ItvDate            string `json:"itv_date"` // DD/MM/YYYY
	Owners             int    `json:"owners"`
}

var reCMToken = regexp.MustCompile(`id="_g_tk"\s+value="([^"]+)"`)

// fetchComprobarMatricula implements the two-step flow: (1) GET the plate page
// to harvest the _g_tk token, (2) GET /api/vehiculo.php with that token.
// Returns (vehicle, ok, rateLimited, error). rateLimited=true means the server
// responded with {"ok":0,"limit":true} — the IP has hit CM's anti-scrape budget.
func (r *esPlateResolver) fetchComprobarMatricula(ctx context.Context, plate string) (cmVehiculo, bool, bool, error) {
	pageURL := r.cmBase + "/matricula/" + url.PathEscape(plate) + "/"

	// Use a per-request cookie jar. The site sets anti-scrape cookies on the
	// page hit that the API endpoint validates; without them the API answers
	// "limit" even on the first call.
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Timeout: r.client.Timeout,
		Jar:     jar,
	}

	// Step 1 — fetch page for token.
	pageBody, _, err := plateRetry(ctx, 2, func() ([]byte, int, error) {
		req, rerr := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
		if rerr != nil {
			return nil, 0, rerr
		}
		req.Header.Set("User-Agent", plateUA)
		req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
		req.Header.Set("Accept-Language", "es-ES,es;q=0.9,en;q=0.5")
		resp, rerr := client.Do(req)
		if rerr != nil {
			return nil, 0, rerr
		}
		defer resp.Body.Close()
		b, rerr := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
		return b, 200, rerr // CM returns HTTP 404 even on success; normalise.
	})
	if err != nil {
		return cmVehiculo{}, false, false, fmt.Errorf("comprobarmatricula page: %w", err)
	}

	m := reCMToken.FindSubmatch(pageBody)
	if len(m) < 2 {
		return cmVehiculo{}, false, false, fmt.Errorf("comprobarmatricula: token not found in page")
	}
	token := string(m[1])

	// Step 2 — call JSON API with token and same jar (cookies attached
	// automatically by the client).
	apiURL := r.cmBase + "/api/vehiculo.php?m=" +
		url.QueryEscape(plate) +
		"&_tk=" + url.QueryEscape(token) +
		"&_hp="

	body, status, err := plateRetry(ctx, 2, func() ([]byte, int, error) {
		req, rerr := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
		if rerr != nil {
			return nil, 0, rerr
		}
		req.Header.Set("User-Agent", plateUA)
		req.Header.Set("Referer", pageURL)
		req.Header.Set("Accept", "application/json")
		req.Header.Set("X-Requested-With", "XMLHttpRequest")
		resp, rerr := client.Do(req)
		if rerr != nil {
			return nil, 0, rerr
		}
		defer resp.Body.Close()
		b, rerr := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
		return b, resp.StatusCode, rerr
	})
	if err != nil {
		return cmVehiculo{}, false, false, fmt.Errorf("comprobarmatricula api: %w", err)
	}
	if status != http.StatusOK {
		return cmVehiculo{}, false, false, fmt.Errorf("comprobarmatricula api: HTTP %d", status)
	}

	var v cmVehiculo
	if err := json.Unmarshal(body, &v); err != nil {
		return cmVehiculo{}, false, false, fmt.Errorf("comprobarmatricula decode: %w", err)
	}
	if v.OK != 1 {
		// {"ok":0,"limit":true} → server IP has been rate-limited (per-IP
		// anti-scrape bucket, documented in ES_ENDPOINTS.md). Surface this
		// so the caller can show "rate-limited" instead of pretending only
		// DGT was queried.
		return cmVehiculo{}, false, v.Limit, nil
	}
	return v, true, false, nil
}

// applyCMToResult maps a comprobarmatricula record onto PlateResult. Existing
// fields on result (e.g. EnvironmentalBadge set by DGT) are preserved.
func applyCMToResult(v cmVehiculo, result *PlateResult) {
	if result.VIN == "" {
		result.VIN = strings.ToUpper(strings.TrimSpace(v.VIN))
	}
	if result.Make == "" {
		result.Make = firstNonEmpty(v.MarcaOficial, v.Brand)
	}
	if result.Model == "" {
		result.Model = firstNonEmpty(v.ModeloCompleto, v.Model)
	}
	if result.Variant == "" {
		result.Variant = v.Version
	}
	if result.FuelType == "" && v.Fuel != "" {
		result.FuelType = v.Fuel
	}
	if result.PowerKW == 0 && v.PotenciaKW > 0 {
		result.PowerKW = float64(v.PotenciaKW)
	}
	if result.PowerCV == 0 && v.PotenciaCV > 0 {
		result.PowerCV = v.PotenciaCV
	}
	if result.DisplacementCC == 0 {
		result.DisplacementCC = parseCCString(v.CilindradaCC)
	}
	if result.BodyType == "" && v.Carroceria != "" {
		result.BodyType = v.Carroceria
	}
	if result.Transmission == "" && v.Caja != "" {
		result.Transmission = v.Caja
	}
	if result.EngineCode == "" && v.CodigoMotor != "" {
		result.EngineCode = strings.ToUpper(strings.TrimSpace(v.CodigoMotor))
	}
	if result.PreviousOwners == 0 && v.Owners > 0 {
		result.PreviousOwners = v.Owners
	}
	if result.ModelYear == 0 {
		if n := parsePositiveInt(v.AnneeModelo); n > 0 {
			result.ModelYear = n
		}
	}
	if result.FirstRegistration == nil {
		if t := parseESDate(v.FechaMatriculacion); !t.IsZero() {
			result.FirstRegistration = &t
		}
	}
	if result.NextInspectionDate == nil {
		if t := parseESDate(v.ItvDate); !t.IsZero() {
			result.NextInspectionDate = &t
		}
	}
}

// parsePositiveInt returns the integer value of s, or 0 if not parseable or non-positive.
func parsePositiveInt(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	var n int
	if _, err := fmt.Sscanf(s, "%d", &n); err != nil {
		return 0
	}
	if n <= 0 {
		return 0
	}
	return n
}

// parseESDate parses DD/MM/YYYY → time.Time; returns zero time on failure.
func parseESDate(s string) time.Time {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Time{}
	}
	t, err := time.Parse("02/01/2006", s)
	if err != nil {
		return time.Time{}
	}
	return t
}

// parseCCString pulls the leading integer out of strings like "1968 cc".
var reCC = regexp.MustCompile(`(\d+)`)

func parseCCString(s string) int {
	m := reCC.FindString(s)
	if m == "" {
		return 0
	}
	var n int
	fmt.Sscanf(m, "%d", &n)
	return n
}

func firstNonEmpty(a ...string) string {
	for _, s := range a {
		if strings.TrimSpace(s) != "" {
			return strings.TrimSpace(s)
		}
	}
	return ""
}

// ── DGT distintivo ambiental ──────────────────────────────────────────────────

// fetchDGTDistintivo queries the DGT environmental badge using the public GET form.
// URL: GET sede.dgt.gob.es/.../distintivo-ambiental/index.html?matricula={PLATE}
// No authentication or CAPTCHA required.
// Response HTML contains badge in SVG filename: distintivo_{BADGE}_sin_fondo.svg
func (r *esPlateResolver) fetchDGTDistintivo(ctx context.Context, plate string, result *PlateResult) error {
	pageBase := r.dgtBase
	queryURL := pageBase + "index.html?matricula=" + url.QueryEscape(plate)

	body, status, err := plateRetry(ctx, 2, func() ([]byte, int, error) {
		req, rerr := http.NewRequestWithContext(ctx, http.MethodGet, queryURL, nil)
		if rerr != nil {
			return nil, 0, rerr
		}
		req.Header.Set("User-Agent", plateUA)
		req.Header.Set("Referer", pageBase)
		req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
		resp, rerr := r.client.Do(req)
		if rerr != nil {
			return nil, 0, rerr
		}
		defer resp.Body.Close()
		b, rerr := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
		return b, resp.StatusCode, rerr
	})
	if err != nil {
		return fmt.Errorf("%w: DGT distintivo unreachable: %v", ErrPlateResolutionUnavailable, err)
	}
	if status != http.StatusOK {
		return fmt.Errorf("%w: DGT distintivo HTTP %d", ErrPlateResolutionUnavailable, status)
	}

	return parseDGTDistintivoResponse(string(body), result)
}

// parseDGTDistintivoResponse extracts the environmental badge from DGT HTML.
// Badge is embedded in SVG filename: "distintivo_C_sin_fondo.svg",
// or in text: "Distintivo Ambiental C."
func parseDGTDistintivoResponse(body string, result *PlateResult) error {
	upper := strings.ToUpper(body)

	// Not found.
	if strings.Contains(upper, "NO SE HA ENCONTRADO") {
		return nil
	}

	// Extract badge from SVG filename: "DISTINTIVO_C_SIN_FONDO.SVG" or "DISTINTIVO_CERO_SIN_FONDO.SVG"
	for _, badge := range []string{"CERO", "ECO", "C", "B"} {
		needle := "DISTINTIVO_" + badge + "_SIN_FONDO"
		if strings.Contains(upper, needle) {
			if badge == "CERO" {
				result.EnvironmentalBadge = "0"
			} else {
				result.EnvironmentalBadge = badge
			}
			break
		}
	}

	// Fallback: parse from text "Distintivo Ambiental C."
	if result.EnvironmentalBadge == "" {
		for _, badge := range []string{"0", "ECO", "C", "B"} {
			if strings.Contains(upper, "DISTINTIVO AMBIENTAL "+badge+".") ||
				strings.Contains(upper, "DISTINTIVO AMBIENTAL "+badge+" ") {
				result.EnvironmentalBadge = badge
				break
			}
		}
	}

	if result.EnvironmentalBadge == "" {
		return fmt.Errorf("no badge found in DGT distintivo response")
	}
	return nil
}

// ── shared helpers (also used by other resolvers) ─────────────────────────────

// extractHiddenFields parses <input type="hidden" name="..." value="..."> from HTML
// and populates vals.
func extractHiddenFields(html string, vals url.Values) {
	lower := strings.ToLower(html)
	search := `type="hidden"`
	pos := 0
	for {
		idx := strings.Index(lower[pos:], search)
		if idx < 0 {
			break
		}
		idx += pos
		start := strings.LastIndex(lower[:idx], "<input")
		if start < 0 {
			pos = idx + len(search)
			continue
		}
		end := strings.Index(lower[idx:], ">")
		if end < 0 {
			pos = idx + len(search)
			continue
		}
		tag := html[start : idx+end+1]
		name := htmlTagAttr(tag, "name")
		value := htmlTagAttr(tag, "value")
		if name != "" {
			vals.Set(name, value)
		}
		pos = idx + len(search)
	}
}

// htmlTagAttr extracts the value of a named attribute from an HTML tag string.
func htmlTagAttr(tag, attr string) string {
	lowerTag := strings.ToLower(tag)
	for _, quote := range []string{`"`, `'`} {
		needle := attr + `=` + quote
		i := strings.Index(lowerTag, needle)
		if i < 0 {
			continue
		}
		i += len(needle)
		j := strings.Index(tag[i:], quote)
		if j < 0 {
			continue
		}
		return tag[i : i+j]
	}
	return ""
}

// Regexes for date extraction (compiled once at package level).
var (
	reDateISO = regexp.MustCompile(`(\d{4})-(\d{2})-(\d{2})`)
	reDateDMY = regexp.MustCompile(`(\d{2})/(\d{2})/(\d{4})`)
)

// extractDateAfterMarker looks for a date string in body after the first occurrence of marker.
func extractDateAfterMarker(body, marker string) time.Time {
	i := strings.Index(body, marker)
	if i < 0 {
		return time.Time{}
	}
	sub := body[i:]
	if m := reDateISO.FindStringSubmatch(sub); len(m) == 4 {
		t, _ := time.Parse("2006-01-02", m[1]+"-"+m[2]+"-"+m[3])
		return t
	}
	if m := reDateDMY.FindStringSubmatch(sub); len(m) == 4 {
		t, _ := time.Parse("02/01/2006", m[1]+"/"+m[2]+"/"+m[3])
		return t
	}
	return time.Time{}
}
