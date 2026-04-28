package check

// plate_fr_api.go — French plate lookup via apiplaqueimmatriculation.com
//
// apiplaqueimmatriculation.com proxies the French SIV (Système d'Immatriculation
// des Véhicules) returning ~30 technical fields per plate.
//
// Returns: marque, modele, VIN, date1erCir, co2, energieNGC, couleur, poids,
//          nb_portes, carrosserieCG, boite_vitesse, code_moteur, cylindres,
//          puisFisc, sra_id, k_type, tecdoc_carid
//
// Configure via env var: FR_PLATE_API_KEY=<your-token>
// Register at: https://apiplaqueimmatriculation.com
// Pricing: from €39/month, no query limit at plan level
//
// API endpoint:
//   POST https://api.apiplaqueimmatriculation.com/plaque
//        ?immatriculation={PLATE}&token={TOKEN}&pays=FR

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type frAPIResponse struct {
	Marque         string `json:"marque"`
	Modele         string `json:"modele"`
	Energie        string `json:"energie"`
	EnergieNGC     string `json:"energieNGC"`
	Date1erCirFR   string `json:"date1erCir_fr"`  // DD-MM-YYYY
	Date1erCirISO  string `json:"date1erCir"`      // YYYY-MM-DD
	VIN            string `json:"vin"`
	Couleur        string `json:"couleur"`
	CO2            string `json:"co2"`
	PuisFisc       string `json:"puisFisc"`
	PuisFiscReel   string `json:"puisFiscReel"` // "130 KW"
	BoiteVitesse   string `json:"boite_vitesse"`
	NbPortes       string `json:"nb_portes"`
	Cylindres      string `json:"cylindres"`
	Carrosserie    string `json:"carrosserieCG"`
	CodeMoteur     string `json:"code_moteur"`
	SRAID          string `json:"sra_id"`
	KType          string `json:"k_type"`
	TecDocCarID    string `json:"tecdoc_carid"`
	Erreur         string `json:"erreur"`
	Message        string `json:"message"`
}

// frAPIResolver wraps apiplaqueimmatriculation.com.
type frAPIResolver struct {
	client *http.Client
	token  string
	base   *frPlateResolver // SSR fallback when API fails
}

func newFRAPIResolver(client *http.Client, token string) *frAPIResolver {
	return &frAPIResolver{
		client: client,
		token:  token,
		base:   newFRPlateResolver(client),
	}
}

func (r *frAPIResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateFRPlate(plate); err != nil {
		return nil, err
	}

	apiURL := fmt.Sprintf(
		"https://api.apiplaqueimmatriculation.com/plaque?immatriculation=%s&token=%s&pays=FR",
		url.QueryEscape(plate), url.QueryEscape(r.token),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("FR API request: %w", err)
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "application/json")

	resp, err := r.client.Do(req)
	if err != nil {
		// Network error — fall back to SSR scraper
		return r.base.Resolve(ctx, plate)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return r.base.Resolve(ctx, plate)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return r.base.Resolve(ctx, plate)
	}

	var data frAPIResponse
	if err := json.Unmarshal(body, &data); err != nil || data.Marque == "" {
		return r.base.Resolve(ctx, plate)
	}

	if data.Erreur != "" || strings.Contains(strings.ToLower(data.Message), "error") {
		return nil, fmt.Errorf("%w: FR plate %s — %s", ErrPlateNotFound, plate, data.Message)
	}

	result := &PlateResult{
		Plate:     plate,
		Country:   "FR",
		Make:      strings.TrimSpace(data.Marque),
		Model:     strings.TrimSpace(data.Modele),
		VIN:       strings.TrimSpace(data.VIN),
		Color:     strings.TrimSpace(data.Couleur),
		BodyType:  strings.TrimSpace(data.Carrosserie),
		EngineCode: strings.TrimSpace(data.CodeMoteur),
		Source:    "apiplaqueimmatriculation.com (SIV)",
		FetchedAt: time.Now().UTC(),
	}

	result.FuelType = normaliseFRFuel(data.EnergieNGC)

	if data.Date1erCirISO != "" {
		t, err := time.Parse("2006-01-02", data.Date1erCirISO)
		if err == nil {
			result.FirstRegistration = &t
		}
	} else if data.Date1erCirFR != "" {
		t, err := time.Parse("02-01-2006", data.Date1erCirFR)
		if err == nil {
			result.FirstRegistration = &t
		}
	}

	if co2, err := strconv.ParseFloat(strings.TrimSpace(data.CO2), 64); err == nil && co2 > 0 {
		result.CO2GPerKm = co2
	}

	if cyl, err := strconv.Atoi(strings.TrimSpace(data.Cylindres)); err == nil && cyl > 0 {
		result.NumberOfCylinders = cyl
	}
	if doors, err := strconv.Atoi(strings.TrimSpace(data.NbPortes)); err == nil && doors > 0 {
		result.NumberOfDoors = doors
	}

	// PuisFiscReel: "130 KW"
	if data.PuisFiscReel != "" {
		parts := strings.Fields(data.PuisFiscReel)
		if len(parts) >= 1 {
			if kw, err := strconv.ParseFloat(parts[0], 64); err == nil && kw > 0 {
				result.PowerKW = kw
			}
		}
	}

	result.Transmission = normaliseFRTransmission(data.BoiteVitesse)

	result.Partial = result.Make == ""
	return result, nil
}

func normaliseFRFuel(s string) string {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "DIESEL", "GAZOLE":
		return "Diesel"
	case "ESSENCE", "SP95", "SP98", "E10", "E85":
		return "Essence"
	case "HYBRIDE RECHARGEABLE ESSENCE", "HYBRIDE RECHARGEABLE":
		return "Hybrid (Essence)"
	case "HYBRIDE RECHARGEABLE DIESEL":
		return "Hybrid (Diesel)"
	case "ELECTRIQUE", "EL":
		return "Électrique"
	case "GPL":
		return "GPL"
	case "GNV", "GNC":
		return "GNV"
	case "HYDROGENE":
		return "Hydrogène"
	}
	return s
}

func normaliseFRTransmission(s string) string {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "M", "MAN", "MANUELLE":
		return "Manuelle"
	case "A", "AUTO", "AUTOMATIQUE":
		return "Automatique"
	case "S", "SEMI":
		return "Semi-automatique"
	case "C", "CVT":
		return "CVT"
	}
	return s
}
