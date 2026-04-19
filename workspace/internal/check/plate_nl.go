package check

// NL plate resolver — RDW Open Data (Rijksdienst voor het Wegverkeer)
//
// Source:   opendata.rdw.nl — no API key required.
// Dataset:  m9d7-ebf2  "Gekentekende voertuigen" (primary vehicle register)
//           sgfe-77wx  "APK / MOT inspections" (queried by kenteken)
// Rate-limit: ≤1 req/sec per Socrata terms of service.
//
// What this returns:
//   - VIN (voertuigidentificatienummer) — full 17-char chassis number
//   - Make, model, body type, color, seats
//   - Fuel type, displacement, power (kW), CO2 (g/km)
//   - Empty weight / gross weight (kg)
//   - First registration date
//   - APK (MOT) expiry date → NextInspectionDate
//   - Last APK date + result → LastInspectionDate / LastInspectionResult

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// nlPlateResolver is the concrete NL resolver.
type nlPlateResolver struct {
	client  *http.Client
	baseURL string // e.g. "https://opendata.rdw.nl/resource"
}

func newNLPlateResolver(client *http.Client, baseURL string) *nlPlateResolver {
	return &nlPlateResolver{client: client, baseURL: baseURL}
}

// NewNLPlateResolverWithBase creates an NLPlateResolver at a custom base URL (tests).
func NewNLPlateResolverWithBase(baseURL string) *nlPlateResolver {
	return &nlPlateResolver{
		client:  newPlateHTTPClient(5 * time.Second),
		baseURL: baseURL,
	}
}

// rdwPlateVehicle captures the full set of m9d7-ebf2 fields available by kenteken.
// Field names follow the RDW open-data catalogue (opendata.rdw.nl); update here
// if RDW renames a field.
type rdwPlateVehicle struct {
	Kenteken                       string `json:"kenteken"`
	VIN                            string `json:"voertuigidentificatienummer"`
	Merk                           string `json:"merk"`
	Handelsbenaming                string `json:"handelsbenaming"`
	Inrichting                     string `json:"inrichting"`    // body type
	EersteKleur                    string `json:"eerste_kleur"`  // primary colour
	DatumEersteToelating           string `json:"datum_eerste_toelating"`             // YYYYMMDD
	DatumTenaamstelling            string `json:"datum_tenaamstelling"`               // current registration date
	BrandstofOmschrijving          string `json:"brandstof_omschrijving"`
	MassaLeegVoertuig              string `json:"massa_ledig_voertuig"`               // kg
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"`  // kg
	Voertuigsoort                  string `json:"voertuigsoort"`
	CilinderInhoud                 string `json:"cilinderinhoud"`                     // cc
	AantalCilinders                string `json:"aantal_cilinders"`
	AantalZitplaatsen              string `json:"aantal_zitplaatsen"`
	VervaldatumAPK                 string `json:"vervaldatum_apk"`                    // YYYYMMDD
	NettoMaximumvermogen           string `json:"netto_maximumvermogen"`              // kW
	CO2UitstootGecombineerd        string `json:"co2_uitstoot_gecombineerd"`          // g/km
	EuroClassificatie              string `json:"uitstoot_deeltjes_licht"`            // Euro norm proxy
	WamVerzekerd                   string `json:"wam_verzekerd"`                      // "Ja"/"Nee"
	TenaamstellenMogelijk          string `json:"tenaamstellen_mogelijk"`
}

// rdwPlateAPK captures APK inspection rows from sgfe-77wx.
type rdwPlateAPK struct {
	Kenteken       string `json:"kenteken"`
	MeldDatum      string `json:"meld_datum_door_keuringsinstantie_dt"` // ISO 8601
	SoortErkenning string `json:"soort_erkenning_omschrijving"`
	Vervaldatum    string `json:"vervaldatum_keuring_dt"` // ISO 8601
}

// rdwPlateFuel captures fuel/emission rows from the 8ys7-d773 brandstof dataset.
// RDW does NOT include fuel data in the main m9d7-ebf2 dataset; it lives separately.
type rdwPlateFuel struct {
	Kenteken              string `json:"kenteken"`
	BrandstofOmschrijving string `json:"brandstof_omschrijving"`   // e.g. "Benzine"
	Vermogen              string `json:"nettomaximumvermogen"`      // kW
	CO2                   string `json:"co2_uitstoot_gecombineerd"` // g/km
	EuroNorm              string `json:"uitlaatemissieniveau"`      // e.g. "EURO 6"
}

// rdwFuelDS is the RDW Open Data dataset ID for fuel/emission data per vehicle.
// NOTE: despite the name in the older VIN provider (rdwStolenDS), 8ys7-d773 is the
// brandstof (fuel) dataset. The plate resolver uses it for fuel type, power, CO2, and Euro norm.
const rdwFuelDS = "8ys7-d773"

func (r *nlPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	// 1. Fetch primary vehicle record by kenteken.
	vehicle, err := r.fetchVehicleByPlate(ctx, plate)
	if err != nil {
		return nil, err
	}

	result := &PlateResult{
		Plate:             plate,
		Make:              strings.TrimSpace(vehicle.Merk),
		Model:             strings.TrimSpace(vehicle.Handelsbenaming),
		BodyType:          strings.TrimSpace(vehicle.Inrichting),
		Color:             strings.TrimSpace(vehicle.EersteKleur),
		FuelType:          strings.TrimSpace(vehicle.BrandstofOmschrijving),
		DisplacementCC:    parseInt(vehicle.CilinderInhoud),
		NumberOfCylinders: parseInt(vehicle.AantalCilinders),
		NumberOfSeats:     parseInt(vehicle.AantalZitplaatsen),
		EmptyWeightKg:     parseInt(vehicle.MassaLeegVoertuig),
		GrossWeightKg:     parseInt(vehicle.ToegestaneMaximumMassaVoertuig),
		Country:           "NL",
		Source:            "RDW Open Data — m9d7-ebf2 + 8ys7-d773 + sgfe-77wx",
		FetchedAt:         time.Now().UTC(),
	}

	// VIN (voertuigidentificatienummer) is NOT exposed in m9d7-ebf2; set only when present.
	if vin := strings.ToUpper(strings.TrimSpace(vehicle.VIN)); vin != "" {
		result.VIN = vin
	}
	if kw := parseFloat(vehicle.NettoMaximumvermogen); kw > 0 {
		result.PowerKW = kw
	}
	if co2 := parseFloat(vehicle.CO2UitstootGecombineerd); co2 > 0 {
		result.CO2GPerKm = co2
	}
	if t := parseRDWDate(vehicle.DatumEersteToelating); !t.IsZero() {
		result.FirstRegistration = &t
	}
	if t := parseRDWDate(vehicle.VervaldatumAPK); !t.IsZero() {
		result.NextInspectionDate = &t
	}
	switch strings.ToLower(vehicle.WamVerzekerd) {
	case "ja":
		result.RegistrationStatus = "active"
	case "nee":
		result.RegistrationStatus = "uninsured"
	}

	// 2. Enrich with fuel/emission data from brandstof dataset — best-effort.
	if fuel, err := r.fetchFuelByPlate(ctx, plate); err == nil && fuel != nil {
		if result.FuelType == "" {
			result.FuelType = strings.TrimSpace(fuel.BrandstofOmschrijving)
		}
		if result.PowerKW == 0 {
			if kw := parseFloat(fuel.Vermogen); kw > 0 {
				result.PowerKW = kw
			}
		}
		if result.CO2GPerKm == 0 {
			if co2 := parseFloat(fuel.CO2); co2 > 0 {
				result.CO2GPerKm = co2
			}
		}
		if fuel.EuroNorm != "" {
			result.EuroNorm = strings.TrimSpace(fuel.EuroNorm)
		}
	}

	// 3. Enrich with APK (MOT) history — best-effort; failure is non-fatal.
	if inspections, err := r.fetchAPKByPlate(ctx, plate); err == nil && len(inspections) > 0 {
		// Most-recent first.
		latest := inspections[0]
		if t := parseRDWDateTime(latest.MeldDatum); !t.IsZero() {
			result.LastInspectionDate = &t
		}
		if t := parseRDWDateTime(latest.Vervaldatum); !t.IsZero() {
			result.NextInspectionDate = &t // override with precise APK record
			result.LastInspectionResult = "pass"
		} else {
			result.LastInspectionResult = "pending"
		}
	}

	return result, nil
}

func (r *nlPlateResolver) fetchVehicleByPlate(ctx context.Context, plate string) (*rdwPlateVehicle, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=1",
		r.baseURL, rdwVehiclesDS, url.QueryEscape(plate),
	)
	body, status, err := plateRetry(ctx, 2, func() ([]byte, int, error) {
		return plateGetJSON(ctx, r.client, query)
	})
	if err != nil {
		return nil, fmt.Errorf("RDW plate request: %w", err)
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("RDW returned HTTP %d", status)
	}

	var rows []rdwPlateVehicle
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, fmt.Errorf("decode RDW plate response: %w", err)
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("%w: plate %s not in RDW registry", ErrPlateNotFound, plate)
	}
	return &rows[0], nil
}

func (r *nlPlateResolver) fetchAPKByPlate(ctx context.Context, plate string) ([]rdwPlateAPK, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$order=meld_datum_door_keuringsinstantie_dt+DESC&$limit=5",
		r.baseURL, rdwAPKDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW APK request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateAPK
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (r *nlPlateResolver) fetchFuelByPlate(ctx context.Context, plate string) (*rdwPlateFuel, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=1",
		r.baseURL, rdwFuelDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW fuel request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateFuel
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return &rows[0], nil
}
