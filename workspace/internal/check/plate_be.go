package check

// BE plate resolver — Belgium
//
// Investigation summary (exhaustive):
//
// 1. DIV (Direction pour l'Immatriculation des Véhicules / Dienst Inschrijving Voertuigen)
//    - The Belgian national vehicle registration authority.
//    - Portal: myminfin.be / mobilit.belgium.be — requires eID or itsme authentication.
//    - No public unauthenticated plate lookup.
//    - NOTE: Belgian plates are PERSONAL (go with the owner, not the vehicle).
//      This complicates lookup: the same plate can be transferred to a different vehicle.
//
// 2. GOCA (Groupement Organisme Agréé de Contrôle Automobile)
//    - Manages technical inspection (contrôle technique) in Wallonie + Brussels.
//    - Portal: goca.be — has a "recherche par immatriculation" public form.
//    - Returns: last inspection date, result (pass/fail), next due date.
//    - Sometimes exposes vehicle type (marque/modèle) in the result.
//    - Endpoint probed: https://www.goca.be/fr/outil-de-recherche + POST with matricule=<PLATE>
//    - Also tried: https://www.goca.be/api/v1/vehicule?plaque=<PLATE> (JSON API if it exists)
//
// 3. DEKRA / Vinçotte / Autosécurité (Flanders)
//    - Flanders uses different inspection organisations. No public API.
//
// 4. Car-Pass (car-pass.be)
//    - Provides odometer history by chassis number (VIN). NOT by plate.
//    - API: https://www.car-pass.be/api/report/{chassis_number}
//    - If GOCA exposes the chassis number in its response, we chain to Car-Pass.
//    - Car-Pass API is semi-public: GET /ecommerce/report/{vin} returns a JSON report.
//
// 5. Motorimmatriculation.be, autovlan.be, 2ememain.be
//    - Consumer platforms, not government sources. Scraped plates from listings only.
//
// What VIN availability: Car-Pass gives full odometer history BY VIN. If we get a chassis
// number from GOCA, we can provide full km history. Otherwise no VIN from public BE sources.
//
// What this resolver returns:
//   - From GOCA: last inspection date, result, next due date, possibly make/model
//   - From Car-Pass (if chassis known): odometer history → MileageKm + MileageDate
//   - VIN: available only if GOCA exposes the chassis number in its response

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type bePlateResolver struct {
	client *http.Client
}

func newBEPlateResolver(client *http.Client) *bePlateResolver {
	return &bePlateResolver{client: client}
}

// validateBEPlate validates Belgian plate format.
// Current format (since 2010): 1 letter + 3 digits + 3 letters → normalised: "1ABC123"
// Old format (pre-2010): 3 letters + 3 digits → "ABC123"
// Personalised: various, up to 8 chars.
func validateBEPlate(plate string) error {
	if len(plate) < 4 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid BE plate length %d", ErrPlateNotFound, len(plate))
	}
	for _, r := range plate {
		if !((r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return fmt.Errorf("%w: invalid character in BE plate", ErrPlateNotFound)
		}
	}
	return nil
}

func (b *bePlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateBEPlate(plate); err != nil {
		return nil, err
	}

	result := &PlateResult{
		Plate:     plate,
		Country:   "BE",
		Source:    "GOCA (contrôle technique Wallonie/Bruxelles)",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}

	// Step 1: GOCA inspection lookup.
	chassisFromGOCA, gocaErr := b.fetchGOCA(ctx, plate, result)

	// Step 2: If we have a chassis number, enrich with Car-Pass odometer history.
	if chassisFromGOCA != "" {
		result.VIN = strings.ToUpper(chassisFromGOCA)
		b.fetchCarPass(ctx, chassisFromGOCA, result)
	}

	if gocaErr != nil && result.LastInspectionDate == nil {
		// GOCA failed and we got nothing.
		return nil, fmt.Errorf(
			"%w: Belgium (BE) — GOCA portal error (%v). "+
				"DIV requires eID auth. Belgian plates are personal (not vehicle-bound). "+
				"Investigated: goca.be, mobilit.belgium.be, car-pass.be",
			ErrPlateResolutionUnavailable, gocaErr,
		)
	}

	if result.LastInspectionDate != nil || result.VIN != "" {
		result.Partial = false
	}

	return result, nil
}

// fetchGOCA probes the GOCA vehicle search by plate.
// Returns the chassis number if GOCA includes it in the response.
func (b *bePlateResolver) fetchGOCA(ctx context.Context, plate string, result *PlateResult) (string, error) {
	const gocaBase = "https://www.goca.be"

	// Normalise plate to Belgian display format: try "X-XXX-XXX" for new format
	// and "XXX-XXX" for old format, since GOCA's form might require the dashes.
	displayPlate := toBEDisplayPlate(plate)

	// POST to GOCA search form.
	formData := url.Values{}
	formData.Set("matricule", displayPlate)
	formData.Set("plaque", displayPlate)       // alternate field name seen on some versions
	formData.Set("immatriculation", plate)      // numeric variant

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		gocaBase+"/fr/outil-de-recherche",
		strings.NewReader(formData.Encode()),
	)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Referer", gocaBase+"/fr/outil-de-recherche")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

	resp, err := b.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("GOCA POST: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return "", fmt.Errorf("GOCA read: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("GOCA HTTP %d", resp.StatusCode)
	}

	return parseGOCAResponse(string(bodyBytes), result), nil
}

// parseGOCAResponse extracts inspection data (and optionally chassis) from GOCA HTML.
func parseGOCAResponse(body string, result *PlateResult) string {
	// GOCA result page typically contains a table with:
	// - Marque / Modèle
	// - Date du dernier contrôle
	// - Résultat (favorable / défavorable)
	// - Date de validité / prochain contrôle
	// - Numéro de châssis (sometimes)

	upper := strings.ToUpper(body)

	// Vehicle make/model
	if v := htmlExtractAfter(body, "Marque", "<td", "</td>"); v != "" {
		result.Make = stripHTMLTags(v)
	} else if v := htmlExtractAfter(upper, "MARQUE", "<TD", "</TD>"); v != "" {
		result.Make = stripHTMLTags(v)
	}
	if v := htmlExtractAfter(body, "Modèle", "<td", "</td>"); v != "" {
		result.Model = stripHTMLTags(v)
	} else if v := htmlExtractAfter(upper, "MODELE", "<TD", "</TD>"); v != "" {
		result.Model = stripHTMLTags(v)
	}

	// Last inspection date
	for _, marker := range []string{"Dernier contrôle", "Date du contrôle", "DERNIER CONTROLE"} {
		if d := extractDateAfterMarker(upper, strings.ToUpper(marker)); !d.IsZero() {
			result.LastInspectionDate = &d
			break
		}
	}

	// Inspection result
	if strings.Contains(upper, "FAVORABLE") && !strings.Contains(upper, "DEFAVORABLE") {
		result.LastInspectionResult = "pass"
	} else if strings.Contains(upper, "DEFAVORABLE") || strings.Contains(upper, "REFUS") {
		result.LastInspectionResult = "fail"
	}

	// Next inspection date
	for _, marker := range []string{"Prochain contrôle", "Valide jusqu", "PROCHAIN CONTROLE"} {
		if d := extractDateAfterMarker(upper, strings.ToUpper(marker)); !d.IsZero() {
			result.NextInspectionDate = &d
			break
		}
	}

	// Chassis number (VIN) — GOCA sometimes shows it.
	chassis := ""
	for _, marker := range []string{"Châssis", "Chassis", "Numéro de châssis", "CHASSIS"} {
		if v := htmlExtractAfter(body, marker, "<td", "</td>"); v != "" {
			candidate := stripHTMLTags(v)
			if len(candidate) >= 11 {
				chassis = candidate
				break
			}
		}
	}
	return chassis
}

// gocaAPIResponse is the shape of GOCA's JSON API (if it exists).
type gocaAPIResponse struct {
	Plaque     string `json:"plaque"`
	Marque     string `json:"marque"`
	Modele     string `json:"modele"`
	Chassis    string `json:"chassis"`
	DernierCT  string `json:"dernierControle"` // ISO date
	Resultat   string `json:"resultat"`
	ProchainCT string `json:"prochainControle"` // ISO date
}

// fetchCarPass queries the Car-Pass odometer history API by chassis/VIN.
// Car-Pass API: GET https://www.car-pass.be/ecommerce/report/{chassis}
// Returns mileage history as JSON.
func (b *bePlateResolver) fetchCarPass(ctx context.Context, chassis string, result *PlateResult) {
	apiURL := fmt.Sprintf("https://www.car-pass.be/ecommerce/report/%s", url.PathEscape(chassis))

	body, status, err := plateRetry(ctx, 1, func() ([]byte, int, error) {
		return plateGetJSON(ctx, b.client, apiURL)
	})
	if err != nil || status != http.StatusOK {
		return
	}

	var report carPassReport
	if err := json.Unmarshal(body, &report); err != nil {
		return
	}

	// Car-Pass returns a list of mileage readings sorted by date.
	if len(report.Mileages) > 0 {
		latest := report.Mileages[len(report.Mileages)-1]
		result.MileageKm = latest.Mileage
		if t, err := time.Parse("2006-01-02", latest.Date); err == nil {
			result.MileageDate = &t
		}
		result.Source += " + Car-Pass (car-pass.be)"
	}
}

type carPassReport struct {
	Chassis  string `json:"chassisNumber"`
	Mileages []struct {
		Date    string `json:"date"`
		Mileage int    `json:"mileage"`
	} `json:"mileageReadings"`
}

// toBEDisplayPlate converts a normalised BE plate (no spaces/dashes) to display format.
// New format (7 chars: 1L-3D-3L): "1ABC123" → "1-ABC-123"
// Old format (6 chars: 3L-3D): "ABC123" → "ABC-123"
func toBEDisplayPlate(plate string) string {
	switch len(plate) {
	case 7:
		// New Belgian format: digit + 3 letters + 3 digits → "D-LLL-DDD"
		// OR letter + 3 digits + 3 letters → "L-DDD-LLL"
		return plate[0:1] + "-" + plate[1:4] + "-" + plate[4:]
	case 6:
		return plate[0:3] + "-" + plate[3:]
	default:
		return plate
	}
}
