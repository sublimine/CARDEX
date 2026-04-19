package check

// ES plate resolver — Spain
//
// Data sources:
//
// 1. DGT Distintivo Ambiental (sede.dgt.gob.es) — PUBLIC, no auth required.
//    GET sede.dgt.gob.es/.../distintivo-ambiental/index.html?matricula={PLATE}
//    Returns: environmental badge (0/ECO/C/B) embedded in HTML.
//    Not-found: "No se ha encontrado ningún resultado".
//
// 2. infocar.dgt.es — as of 2025 requires Cl@ve/certificado. Skipped.
//
// 3. ITV portals: each of Spain's 17 CCAA runs its own system, none public.
//
// 4. Commercial resellers (autoficha, cartell, etc.): not freely accessible.
//
// VIN availability: NOT available from any public Spanish source.
//
// What this resolver returns (partial):
//   - Environmental badge (0 / ECO / C / B)

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
		Source:    "DGT Sede Electrónica — distintivo ambiental (sede.dgt.gob.es)",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	// DGT Distintivo Ambiental — public GET form, no auth required.
	etiquetaErr := r.fetchDGTDistintivo(ctx, plate, result)

	if result.EnvironmentalBadge == "" {
		if etiquetaErr != nil {
			return nil, fmt.Errorf("%w: DGT distintivo error: %v", ErrPlateResolutionUnavailable, etiquetaErr)
		}
		return nil, fmt.Errorf("%w: DGT returned no data for plate %s — plate not found or no label assigned", ErrPlateNotFound, plate)
	}

	result.Partial = false
	return result, nil
}

// fetchDGTDistintivo queries the DGT environmental badge using the public GET form.
// URL: GET sede.dgt.gob.es/.../distintivo-ambiental/index.html?matricula={PLATE}
// No authentication or CAPTCHA required.
// Response HTML contains badge in SVG filename: distinctivo_{BADGE}_sin_fondo.svg
func (r *esPlateResolver) fetchDGTDistintivo(ctx context.Context, plate string, result *PlateResult) error {
	const pageBase = "https://sede.dgt.gob.es/es/vehiculos/informacion-de-vehiculos/distintivo-ambiental/"
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
		return nil // return nil — Resolve will emit ErrPlateNotFound
	}

	// Extract badge from SVG filename: "DISTINTIVO_C_SIN_FONDO.SVG" or "DISTINTIVO_CERO_SIN_FONDO.SVG"
	for _, badge := range []string{"CERO", "ECO", "C", "B"} {
		needle := "DISTINTIVO_" + badge + "_SIN_FONDO"
		if strings.Contains(upper, needle) {
			if badge == "CERO" {
				result.EnvironmentalBadge = "0"
				result.FuelType = "Eléctrico / Hidrógeno"
			} else {
				result.EnvironmentalBadge = badge
				switch badge {
				case "ECO":
					result.FuelType = "Gas Natural / Híbrido enchufable"
				case "C":
					result.FuelType = "Gasolina o Diésel Euro 6"
				case "B":
					result.FuelType = "Gasolina o Diésel Euro 5"
				}
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
