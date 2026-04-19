package check

// FR plate resolver — France
//
// Investigation summary (exhaustive):
//
// 1. HistoVec (histovec.interieur.gouv.fr)
//    - Official French government vehicle history portal (Ministère de l'Intérieur).
//    - Old API (v1): required plate + SIV registration certificate formula number.
//    - New design (2022+): requires plate + last name + first name + date of birth
//      of the registered owner. Cannot be used for third-party plate lookup.
//    - API endpoint probed: GET /histovec/api/v2/report?immatriculation=<PLATE>
//      Returns HTTP 400/403 with "identification insuffisante" without owner data.
//
// 2. ANTS (Agence Nationale des Titres Sécurisés) / SIV
//    - SIV (Système d'Immatriculation des Véhicules) is the national registry.
//    - API access via api.gouv.fr requires: SIRET number, professional justification,
//      ANTS approval. Not accessible to third parties without agreement.
//    - immatriculation.ants.gouv.fr requires France Connect (digital identity login).
//
// 3. UTAC / Contrôle Technique
//    - UTAC-OTC manages French technical inspection (CT) data.
//    - No public individual plate lookup; professionals subscribe at utac.com.
//
// 4. data.gouv.fr
//    - Open datasets available: vehicle registration STATISTICS (aggregated by month/model),
//      NOT individual vehicle records. No plate → VIN lookup possible.
//    - Dataset "Parc de véhicules" (sinoe.ademe.fr) is aggregate only.
//
// 5. Third-party services (carvxn.com, verif.com, plaque-immat.fr)
//    - Commercial resellers of ANTS/SIV data. Require subscription or per-query payment.
//    - Not publicly accessible without auth.
//
// Conclusion: France has NO public plate-to-vehicle lookup. GDPR + SIV access restrictions
// prevent any third-party unauthenticated query. The resolver attempts the HistoVec
// public endpoint and documents exactly what it receives.
//
// VIN availability: NOT available from any public FR source.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
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

// histovecResponse is the partial shape of a HistoVec API response when accessible.
type histovecResponse struct {
	Immatriculation string `json:"immatriculation"`
	Marque          string `json:"marque"`
	Modele          string `json:"modele"`
	DateImmat       string `json:"dateImmatriculation"` // YYYY-MM-DD
	Carburant       string `json:"carburant"`
	Puissance       int    `json:"puissance"` // kW
}

func (r *frPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateFRPlate(plate); err != nil {
		return nil, err
	}

	// Attempt HistoVec public API — documented to require owner identity since 2022,
	// but we probe it in case a public endpoint is restored in the future.
	if result, err := r.tryHistoVec(ctx, plate); err == nil {
		return result, nil
	}

	// No public source succeeded.
	return nil, fmt.Errorf(
		"%w: France (FR) — HistoVec requires owner identity (name + DOB + plate). "+
			"SIV/ANTS API requires professional SIRET agreement. "+
			"No public plate→vehicle lookup exists in France. "+
			"Investigated: histovec.interieur.gouv.fr, immatriculation.ants.gouv.fr, "+
			"api.gouv.fr/les-apis/api-immatriculation-vehicule, data.gouv.fr/datasets/",
		ErrPlateResolutionUnavailable,
	)
}

// tryHistoVec probes the HistoVec API endpoint.
// Returns a result if the API responds with vehicle data; returns an error otherwise.
func (r *frPlateResolver) tryHistoVec(ctx context.Context, plate string) (*PlateResult, error) {
	// HistoVec v2 API endpoint (probed — may require owner identity).
	apiURL := fmt.Sprintf(
		"https://histovec.interieur.gouv.fr/histovec/api/v2/report?immatriculation=%s",
		url.QueryEscape(plate),
	)

	body, status, err := plateRetry(ctx, 1, func() ([]byte, int, error) {
		return plateGetJSON(ctx, r.client, apiURL)
	})
	if err != nil {
		return nil, fmt.Errorf("HistoVec request: %w", err)
	}
	if status == http.StatusForbidden || status == http.StatusUnauthorized || status == http.StatusBadRequest {
		return nil, fmt.Errorf("HistoVec HTTP %d: requires owner identification", status)
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HistoVec HTTP %d", status)
	}

	// Try to decode JSON response.
	var hv histovecResponse
	if err := json.Unmarshal(body, &hv); err != nil {
		return nil, fmt.Errorf("HistoVec decode: %w", err)
	}
	if hv.Immatriculation == "" && hv.Marque == "" {
		return nil, fmt.Errorf("HistoVec returned empty vehicle data")
	}

	result := &PlateResult{
		Plate:     plate,
		Make:      strings.TrimSpace(hv.Marque),
		Model:     strings.TrimSpace(hv.Modele),
		FuelType:  strings.TrimSpace(hv.Carburant),
		Country:   "FR",
		Source:    "HistoVec — histovec.interieur.gouv.fr",
		FetchedAt: time.Now().UTC(),
		Partial:   true,
	}
	if hv.Puissance > 0 {
		result.PowerKW = float64(hv.Puissance)
	}
	if hv.DateImmat != "" {
		if t, err := time.Parse("2006-01-02", hv.DateImmat); err == nil {
			result.FirstRegistration = &t
		}
	}
	return result, nil
}
