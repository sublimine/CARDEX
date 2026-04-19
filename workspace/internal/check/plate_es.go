package check

// ES plate resolver — Spain
//
// Investigation summary (exhaustive):
//
// 1. DGT Sede Electrónica (sede.dgt.gob.es / infocar.dgt.es)
//    - "Informe de Vehículo" completo: requires Cl@ve or certificado digital. Not accessible.
//    - "Etiqueta Medioambiental DGT": historically a public form that returned the
//      environmental badge (Zero/Eco/C/B) and first-registration date by plate with NO auth.
//      Probed at: POST sede.dgt.gob.es/.../etiqueta-medioambiental/
//      Returns badge type + fuel category when the form responds.
//    - infocar.dgt.es/etrami servlet: GET-based, historically returned make/model/engine data.
//      As of 2024 it redirects to Cl@ve login for full informe; may still return partial data.
//
// 2. DGT TESTRA / GESTAR (B2B API): requires professional agreement + CIF/NIF. Not applicable.
//
// 3. ITV portals (Inspección Técnica de Vehículos):
//    - Each of Spain's 17 autonomous communities runs its own ITV system.
//    - None offer an unauthenticated public plate lookup as of 2025.
//    - ITEVEBASA (Canary Islands), VEIASA (Andalucía), APPLUS+ (Cat/Mad): all require login
//      or provide only station-locator functionality publicly.
//
// 4. autoficha.com, informedeunvehiculo.com, cartell.es:
//    - These are commercial resellers of DGT data via licensed API. Not freely accessible.
//
// What VIN availability: NONE. Spain's DGT does not expose the número de bastidor (VIN)
// in any public endpoint — it is available only to the registered owner via Cl@ve or on
// the physical Permiso de Circulación document.
//
// What this resolver returns (partial):
//   - Environmental badge (Zero / Eco / C / B) → fuel category proxy
//   - First registration date (from DGT etiqueta form)
//   - Make / model / displacement / power (from infocar.dgt.es if accessible)

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

type esPlateResolver struct {
	client *http.Client
}

func newESPlateResolver(client *http.Client) *esPlateResolver {
	return &esPlateResolver{client: client}
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
		Source:    "DGT Sede Electrónica (etiqueta medioambiental, infocar)",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	// Step 1: DGT environmental badge (public, no auth required historically).
	etiquetaErr := r.fetchDGTEtiqueta(ctx, plate, result)

	// Step 2: DGT infocar reduced data (may redirect to login).
	r.fetchDGTInformeReducido(ctx, plate, result)

	// If neither returned anything useful, fail with a clear explanation.
	if result.EnvironmentalBadge == "" && result.Make == "" && result.FirstRegistration == nil {
		if etiquetaErr != nil {
			return nil, fmt.Errorf("%w: DGT portal error (%v) — full data requires Cl@ve login", ErrPlateResolutionUnavailable, etiquetaErr)
		}
		return nil, fmt.Errorf("%w: DGT returned no data for plate %s", ErrPlateResolutionUnavailable, plate)
	}

	// Mark as non-partial if we got at least badge + date.
	if result.EnvironmentalBadge != "" && result.FirstRegistration != nil {
		result.Partial = false
	}

	return result, nil
}

// fetchDGTEtiqueta sends a POST to the DGT environmental-badge form.
// URL: https://sede.dgt.gob.es/sede/procedimientos/tramites-vehiculos/etiqueta-medioambiental/
// Form field: matricula=<PLATE>
// Response: HTML page containing badge class and registration date.
func (r *esPlateResolver) fetchDGTEtiqueta(ctx context.Context, plate string, result *PlateResult) error {
	const baseURL = "https://sede.dgt.gob.es/sede/procedimientos/tramites-vehiculos/etiqueta-medioambiental/"

	// GET the page first to capture hidden form fields / CSRF tokens.
	getBody, status, err := plateRetry(ctx, 2, func() ([]byte, int, error) {
		return plateGetHTML(ctx, r.client, baseURL)
	})
	if err != nil || (status != http.StatusOK && status != http.StatusFound) {
		return fmt.Errorf("DGT etiqueta GET: HTTP %d: %w", status, err)
	}

	// Build POST body with plate + any hidden fields extracted from the form.
	formData := url.Values{}
	formData.Set("matricula", plate)
	extractHiddenFields(string(getBody), formData)

	// POST the form.
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL, strings.NewReader(formData.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Referer", baseURL)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

	resp, err := r.client.Do(req)
	if err != nil {
		return fmt.Errorf("DGT etiqueta POST: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return fmt.Errorf("DGT etiqueta read: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("DGT etiqueta POST: HTTP %d", resp.StatusCode)
	}

	return parseDGTEtiquetaResponse(string(bodyBytes), result)
}

// parseDGTEtiquetaResponse extracts badge + date from the DGT etiqueta HTML.
// The DGT page contains spans/divs with class names like "etiqueta-ZERO", "etiqueta-ECO", etc.
func parseDGTEtiquetaResponse(body string, result *PlateResult) error {
	upper := strings.ToUpper(body)

	for _, badge := range []string{"ZERO", "ECO", "C", "B"} {
		if strings.Contains(upper, "ETIQUETA-"+badge) ||
			strings.Contains(upper, "ETIQUETA "+badge) ||
			strings.Contains(upper, ">"+badge+"<") {
			result.EnvironmentalBadge = badge
			switch badge {
			case "ZERO":
				result.FuelType = "Eléctrico / Hidrógeno"
			case "ECO":
				result.FuelType = "Gas Natural / Híbrido enchufable"
			case "C":
				result.FuelType = "Gasolina o Diésel Euro 6"
			case "B":
				result.FuelType = "Gasolina o Diésel Euro 5"
			}
			break
		}
	}

	// First registration date — look for DD/MM/YYYY or YYYY-MM-DD near "MATRICULACION"
	if d := extractDateAfterMarker(upper, "PRIMERA MATRICULACION"); !d.IsZero() {
		result.FirstRegistration = &d
	} else if d := extractDateAfterMarker(upper, "MATRICULACION"); !d.IsZero() {
		result.FirstRegistration = &d
	}

	if result.EnvironmentalBadge == "" {
		return fmt.Errorf("no badge found in DGT etiqueta response")
	}
	return nil
}

// fetchDGTInformeReducido attempts the infocar.dgt.es servlet.
// Historically returned make, model, displacement, power without auth.
// As of 2024 it may redirect to login for full data.
func (r *esPlateResolver) fetchDGTInformeReducido(ctx context.Context, plate string, result *PlateResult) {
	informeURL := fmt.Sprintf(
		"https://infocar.dgt.es/etrami/servlet/Anulaciones?accion=InformeVehiculo&matricula=%s",
		url.QueryEscape(plate),
	)

	body, status, err := plateRetry(ctx, 1, func() ([]byte, int, error) {
		return plateGetHTML(ctx, r.client, informeURL)
	})
	if err != nil || status != http.StatusOK || len(body) < 200 {
		return
	}

	s := string(body)
	// Skip if redirected to Cl@ve login.
	if strings.Contains(strings.ToLower(s), "clave") || strings.Contains(strings.ToLower(s), "login") {
		return
	}

	if v := htmlExtractAfter(s, "MARCA", "<td", "</td>"); v != "" {
		result.Make = stripHTMLTags(v)
	}
	if v := htmlExtractAfter(s, "MODELO", "<td", "</td>"); v != "" {
		result.Model = stripHTMLTags(v)
	}
	if v := htmlExtractAfter(s, "CILINDRADA", "<td", "</td>"); v != "" {
		if cc := parseInt(stripHTMLTags(v)); cc > 0 {
			result.DisplacementCC = cc
		}
	}
	if v := htmlExtractAfter(s, "POTENCIA", "<td", "</td>"); v != "" {
		if kw := parseFloat(stripHTMLTags(v)); kw > 0 {
			result.PowerKW = kw
		}
	}
	if v := htmlExtractAfter(s, "COMBUSTIBLE", "<td", "</td>"); v != "" && result.FuelType == "" {
		result.FuelType = stripHTMLTags(v)
	}
}

// ── shared helpers ─────────────────────────────────────────────────────────────

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
