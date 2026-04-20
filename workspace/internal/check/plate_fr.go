package check

// FR plate resolver — immatriculation-auto.info (SSR)
//
// The site renders vehicle data server-side. For any valid French plate
// the SSR HTML always includes:
//   <title>{PLATE} - {Make} {Year}</title>
//   <meta name="description" content="{Make} {Model} immatriculée en France ...
//     couleur extérieure {Color}, son carburant {Fuel}, ... capacité de {CC} cm³">
//
// Not-found detection: page title contains "Téléchargez l'application" instead
// of the plate number.
//
// VIN availability: NOT available from this public source.
// Data available: Make, Model, Year, Color, Fuel type, Displacement CC.

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type frPlateResolver struct {
	client *http.Client
}

func newFRPlateResolver(client *http.Client) *frPlateResolver {
	return &frPlateResolver{client: client}
}

// validateFRPlate validates French plate format.
// Post-2009: AB-123-CD (7 chars normalised: AB123CD)
// Pre-2009 (regional): 123-ABC-12 (various, 5-9 chars)
func validateFRPlate(plate string) error {
	if len(plate) < 5 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid FR plate length %d", ErrPlateNotFound, len(plate))
	}
	for _, r := range plate {
		if !((r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return fmt.Errorf("%w: invalid character in FR plate", ErrPlateNotFound)
		}
	}
	return nil
}

func (r *frPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateFRPlate(plate); err != nil {
		return nil, err
	}

	pageURL := "https://www.immatriculation-auto.info/vehicle/" + plate

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, fmt.Errorf("FR request: %w", err)
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "fr-FR,fr;q=0.9,en;q=0.8")

	resp, err := r.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: immatriculation-auto.info unreachable: %v", ErrPlateResolutionUnavailable, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	if err != nil {
		return nil, fmt.Errorf("FR read: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: immatriculation-auto.info HTTP %d", ErrPlateResolutionUnavailable, resp.StatusCode)
	}

	bodyStr := string(body)

	// Not-found: title doesn't contain the plate.
	title := htmlExtract(bodyStr, "<title>", "</title>")
	if title == "" || !strings.Contains(title, plate) {
		return nil, fmt.Errorf("%w: plate %s not found in FR public registry", ErrPlateNotFound, plate)
	}

	result := &PlateResult{
		Plate:     plate,
		Country:   "FR",
		Source:    "immatriculation-auto.info — registre SIV (scraping SSR)",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	// Parse title: "{PLATE} - {Make} {Year}"
	parsefrTitle(title, plate, result)

	// Parse meta description for richer data.
	metaDesc := extractMetaDescription(bodyStr)
	if metaDesc != "" {
		parseFRMetaDesc(metaDesc, result)
	}

	if result.Make != "" {
		result.Partial = false
	}

	return result, nil
}

// parsefrTitle parses "{PLATE} - {Make} {Year}" from the <title> element.
func parsefrTitle(title, plate string, r *PlateResult) {
	prefix := plate + " - "
	if !strings.HasPrefix(title, prefix) {
		return
	}
	rest := strings.TrimSpace(title[len(prefix):])
	parts := strings.Fields(rest)
	if len(parts) == 0 {
		return
	}
	// Last token may be the year.
	last := parts[len(parts)-1]
	if yr, err := strconv.Atoi(last); err == nil && yr >= 1950 && yr <= 2030 {
		t := time.Date(yr, 1, 1, 0, 0, 0, 0, time.UTC)
		r.FirstRegistration = &t
		r.Make = strings.Join(parts[:len(parts)-1], " ")
	} else {
		r.Make = rest
	}
}

var (
	frReYear = regexp.MustCompile(`\b(19[5-9]\d|20[0-4]\d)\b`)
	frReCC   = regexp.MustCompile(`(\d{3,5})\s*cm`)
)

// parseFRMetaDesc parses vehicle data from the SSR meta description.
// Format: "{Make} {Model} immatriculée en France ... en {Year}.
//
//	Découvrez sa couleur extérieure {Color}, son carburant {Fuel},
//	sa {Transmission} et sa capacité de {CC} cm³"
func parseFRMetaDesc(desc string, r *PlateResult) {
	// Model: text before "immatriculée"
	if idx := strings.Index(desc, " immatriculée"); idx > 0 {
		makeModel := strings.TrimSpace(desc[:idx])
		if r.Make != "" && strings.HasPrefix(makeModel, r.Make) {
			model := strings.TrimSpace(makeModel[len(r.Make):])
			if model != "" && r.Model == "" {
				r.Model = model
			}
		} else if r.Make == "" {
			parts := strings.Fields(makeModel)
			if len(parts) >= 2 {
				r.Make = parts[0]
				r.Model = strings.Join(parts[1:], " ")
			} else {
				r.Make = makeModel
			}
		}
	}

	// First registration year: "immatriculé... en YYYY."
	if r.FirstRegistration == nil {
		if i := strings.Index(desc, " en "); i >= 0 {
			after := desc[i+4:]
			if j := strings.IndexByte(after, '.'); j >= 0 {
				after = after[:j]
			}
			if m := frReYear.FindString(after); m != "" {
				if yr, _ := strconv.Atoi(m); yr > 1950 {
					t := time.Date(yr, 1, 1, 0, 0, 0, 0, time.UTC)
					r.FirstRegistration = &t
				}
			}
		}
	}

	// Color: "couleur extérieure {Color},"
	for _, marker := range []string{"couleur extérieure ", "couleur ext"} {
		if i := strings.Index(desc, marker); i >= 0 {
			after := desc[i+len(marker):]
			// skip possible HTML entity suffix like "&#233;rieure "
			if marker == "couleur ext" {
				if j := strings.Index(after, " "); j >= 0 {
					after = after[j+1:]
				}
			}
			if j := strings.IndexAny(after, ",.\n"); j > 0 {
				r.Color = strings.TrimSpace(after[:j])
			}
			break
		}
	}

	// Fuel: "son carburant {Fuel},"
	if i := strings.Index(desc, "son carburant "); i >= 0 {
		after := desc[i+len("son carburant "):]
		if j := strings.IndexAny(after, ",.\n"); j > 0 {
			r.FuelType = strings.TrimSpace(after[:j])
		}
	}

	// Displacement: "capacité de {CC} cm" or "capacit&#233; de {CC} cm"
	for _, marker := range []string{"capacité de ", "capacit"} {
		if i := strings.Index(desc, marker); i >= 0 {
			after := desc[i:]
			// Skip to the number
			if j := strings.Index(after, " de "); j >= 0 {
				after = after[j+4:]
			}
			if m := frReCC.FindStringSubmatch(after); len(m) >= 2 {
				if cc, err := strconv.Atoi(m[1]); err == nil && cc > 0 {
					r.DisplacementCC = cc
				}
			}
			break
		}
	}
}

// extractMetaDescription finds the content of <meta name="description" content="...">
func extractMetaDescription(body string) string {
	needle := `<meta name="description" content="`
	i := strings.Index(body, needle)
	if i < 0 {
		return ""
	}
	rest := body[i+len(needle):]
	j := strings.IndexByte(rest, '"')
	if j < 0 {
		return ""
	}
	return rest[:j]
}
