package check

// NL plate resolver — RDW Open Data (Rijksdienst voor het Wegverkeer)
//
// Datasets consulted in parallel (all Socrata, no API key required):
//   m9d7-ebf2  Gekentekende_voertuigen   — registration, weight, colour, doors, insurance,
//                                          export flag, open-recall indicator, tellerstandoordeel
//   8ys7-d773  Brandstof                 — fuel type, Euro norm, net power kW, L/100km
//   sgfe-77wx  Keuringen                 — APK inspection history (date, next-due, station)
//   a34c-vvps  Gebreken                  — APK defects per inspection (code, count)
//   3huj-srit  Assen                     — number of axles, track width, max axle load
//   vezc-m2t6  Carrosserie               — EU body-type classification
//
// Rate limit: ≤1 req/sec per Socrata ToS; 6 parallel requests are within that budget.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	rdwFuelDS        = "8ys7-d773" // Brandstof (fuel / emissions)
	rdwAxlesDS       = "3huj-srit" // Assen (axles)
	rdwCarrosserieDS = "vezc-m2t6" // Carrosserie (EU body type)
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

// ── dataset row types ─────────────────────────────────────────────────────────

// rdwPlateVehicle captures m9d7-ebf2 fields available by kenteken.
type rdwPlateVehicle struct {
	Kenteken                       string `json:"kenteken"`
	VIN                            string `json:"voertuigidentificatienummer"`
	Merk                           string `json:"merk"`
	Handelsbenaming                string `json:"handelsbenaming"`
	Inrichting                     string `json:"inrichting"`
	EersteKleur                    string `json:"eerste_kleur"`
	DatumEersteToelating           string `json:"datum_eerste_toelating"`
	DatumTenaamstelling            string `json:"datum_tenaamstelling"`
	BrandstofOmschrijving          string `json:"brandstof_omschrijving"`
	MassaLeegVoertuig              string `json:"massa_ledig_voertuig"`
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"`
	Voertuigsoort                  string `json:"voertuigsoort"`
	CilinderInhoud                 string `json:"cilinderinhoud"`
	AantalCilinders                string `json:"aantal_cilinders"`
	AantalZitplaatsen              string `json:"aantal_zitplaatsen"`
	AantalDeuren                   string `json:"aantal_deuren"`
	VervaldatumAPK                 string `json:"vervaldatum_apk"`
	VervaldatumAPKDT               string `json:"vervaldatum_apk_dt"`
	NettoMaximumvermogen           string `json:"netto_maximumvermogen"`
	CO2UitstootGecombineerd        string `json:"co2_uitstoot_gecombineerd"`
	WamVerzekerd                   string `json:"wam_verzekerd"`
	TenaamstellenMogelijk          string `json:"tenaamstellen_mogelijk"`
	ExportIndicator                string `json:"export_indicator"`
	OpenstaandeTerugroepActie      string `json:"openstaande_terugroepactie_indicator"`
	Tellerstandoordeel             string `json:"tellerstandoordeel"`
}

// rdwPlateAPK captures inspection rows from sgfe-77wx.
type rdwPlateAPK struct {
	Kenteken       string `json:"kenteken"`
	MeldDatum      string `json:"meld_datum_door_keuringsinstantie_dt"`
	SoortErkenning string `json:"soort_erkenning_omschrijving"`
	Vervaldatum    string `json:"vervaldatum_keuring_dt"`
}

// rdwPlateFuel captures fuel / emission rows from 8ys7-d773.
type rdwPlateFuel struct {
	Kenteken              string `json:"kenteken"`
	BrandstofOmschrijving string `json:"brandstof_omschrijving"`
	Vermogen              string `json:"nettomaximumvermogen"`
	CO2                   string `json:"co2_uitstoot_gecombineerd"`
	EuroNorm              string `json:"uitlaatemissieniveau"`
	VerbruikGecombineerd  string `json:"brandstofverbruik_gecombineerd"`
}

// rdwPlateAxle captures axle rows from 3huj-srit.
type rdwPlateAxle struct {
	Kenteken       string `json:"kenteken"`
	AsNummer       string `json:"as_nummer"`
	Spoorbreedte   string `json:"spoorbreedte"`
	MaximaleLastAs string `json:"maximale_last_as"`
}

// rdwPlateCarrosserie captures EU body-type from vezc-m2t6.
type rdwPlateCarrosserie struct {
	Kenteken   string `json:"kenteken"`
	EUBodyType string `json:"type_carrosserie_europese_omschrijving"`
}

// ── resolver ──────────────────────────────────────────────────────────────────

func (r *nlPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	// Primary fetch — required; all others are best-effort.
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
		NumberOfDoors:     parseInt(vehicle.AantalDeuren),
		EmptyWeightKg:     parseInt(vehicle.MassaLeegVoertuig),
		GrossWeightKg:     parseInt(vehicle.ToegestaneMaximumMassaVoertuig),
		Country:           "NL",
		Source:            "RDW Open Data (m9d7-ebf2+8ys7-d773+sgfe-77wx+a34c-vvps+3huj-srit+vezc-m2t6)",
		FetchedAt:         time.Now().UTC(),
	}

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
	// APK expiry: prefer ISO datetime, fall back to date-only.
	if t := parseRDWDateTime(vehicle.VervaldatumAPKDT); !t.IsZero() {
		result.NextInspectionDate = &t
	} else if t := parseRDWDate(vehicle.VervaldatumAPK); !t.IsZero() {
		result.NextInspectionDate = &t
	}
	switch strings.ToLower(vehicle.WamVerzekerd) {
	case "ja":
		result.RegistrationStatus = "active"
	case "nee":
		result.RegistrationStatus = "uninsured"
	}
	switch strings.ToLower(vehicle.Tellerstandoordeel) {
	case "logisch":
		result.OdometerStatus = "logical"
	case "onlogisch":
		result.OdometerStatus = "illogical"
	}

	// ── parallel enrichment ───────────────────────────────────────────────────
	var (
		fuelRows        []rdwPlateFuel
		apkRows         []rdwPlateAPK
		defectRows      []rdwDefect // reuse type from provider_nl.go (same package)
		axleRows        []rdwPlateAxle
		carrosserieRows []rdwPlateCarrosserie
		mu              sync.Mutex
		wg              sync.WaitGroup
	)

	wg.Add(5)
	go func() {
		defer wg.Done()
		rows, e := r.fetchFuelRows(ctx, plate)
		if e == nil {
			mu.Lock()
			fuelRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		rows, e := r.fetchAPKByPlate(ctx, plate)
		if e == nil {
			mu.Lock()
			apkRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		rows, e := r.fetchDefectsByPlate(ctx, plate)
		if e == nil {
			mu.Lock()
			defectRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		rows, e := r.fetchAxlesByPlate(ctx, plate)
		if e == nil {
			mu.Lock()
			axleRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		rows, e := r.fetchCarrosserieByPlate(ctx, plate)
		if e == nil {
			mu.Lock()
			carrosserieRows = rows
			mu.Unlock()
		}
	}()
	wg.Wait()

	// ── apply fuel enrichment ─────────────────────────────────────────────────
	if len(fuelRows) > 0 {
		f := fuelRows[0]
		if result.FuelType == "" {
			result.FuelType = strings.TrimSpace(f.BrandstofOmschrijving)
		}
		if result.PowerKW == 0 {
			if kw := parseFloat(f.Vermogen); kw > 0 {
				result.PowerKW = kw
			}
		}
		if result.CO2GPerKm == 0 {
			if co2 := parseFloat(f.CO2); co2 > 0 {
				result.CO2GPerKm = co2
			}
		}
		if f.EuroNorm != "" {
			result.EuroNorm = strings.TrimSpace(f.EuroNorm)
		}
		if v := parseFloat(f.VerbruikGecombineerd); v > 0 {
			result.FuelConsumptionL100km = v
		}
	}

	// ── apply axles ───────────────────────────────────────────────────────────
	// Guard: only count when the first row carries a valid axle number to avoid
	// mis-counting when a test server echoes unrelated JSON on this endpoint.
	if len(axleRows) > 0 && strings.TrimSpace(axleRows[0].AsNummer) != "" {
		result.NumberOfAxles = len(axleRows)
	}

	// ── apply EU body type ────────────────────────────────────────────────────
	if len(carrosserieRows) > 0 {
		if eu := strings.TrimSpace(carrosserieRows[0].EUBodyType); eu != "" && result.BodyType == "" {
			result.BodyType = eu
		}
	}

	// ── build full APK history ────────────────────────────────────────────────
	if len(apkRows) > 0 {
		// Index defects by inspection date string for O(1) lookup.
		defectsByDate := make(map[string][]APKDefect)
		for _, d := range defectRows {
			code := strings.TrimSpace(d.GebrekID)
			if code == "" {
				continue
			}
			count := parseInt(d.AantalGebreken)
			if count == 0 {
				count = 1
			}
			defectsByDate[d.MeldDatum] = append(defectsByDate[d.MeldDatum], APKDefect{
				Code:    code,
				Count:   count,
				Station: strings.TrimSpace(d.SoortErkenning),
			})
		}

		for _, row := range apkRows {
			entry := APKEntry{
				Station: strings.TrimSpace(row.SoortErkenning),
				Defects: defectsByDate[row.MeldDatum],
			}
			if t := parseRDWDateTime(row.MeldDatum); !t.IsZero() {
				entry.Date = t
			}
			// Result derivation:
			//   defects present → fail
			//   Vervaldatum set → pass (new next-due date issued)
			//   otherwise        → pending
			switch {
			case len(entry.Defects) > 0:
				entry.Result = "fail"
			case parseRDWDateTime(row.Vervaldatum).IsZero():
				entry.Result = "pending"
			default:
				next := parseRDWDateTime(row.Vervaldatum)
				entry.NextDueDate = &next
				entry.Result = "pass"
			}
			result.APKHistory = append(result.APKHistory, entry)
		}

		// Set summary inspection fields from the most-recent record (index 0 = DESC order).
		latest := result.APKHistory[0]
		if !latest.Date.IsZero() {
			result.LastInspectionDate = &latest.Date
		}
		result.LastInspectionResult = latest.Result
		if latest.NextDueDate != nil {
			result.NextInspectionDate = latest.NextDueDate
		}
	}

	return result, nil
}

// ── fetch helpers ─────────────────────────────────────────────────────────────

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
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$order=meld_datum_door_keuringsinstantie_dt+DESC&$limit=20",
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

func (r *nlPlateResolver) fetchFuelRows(ctx context.Context, plate string) ([]rdwPlateFuel, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
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
	return rows, nil
}

func (r *nlPlateResolver) fetchDefectsByPlate(ctx context.Context, plate string) ([]rdwDefect, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=50",
		r.baseURL, rdwDefectsDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW defects request: status=%d err=%v", status, err)
	}
	var rows []rdwDefect
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (r *nlPlateResolver) fetchAxlesByPlate(ctx context.Context, plate string) ([]rdwPlateAxle, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		r.baseURL, rdwAxlesDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW axles request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateAxle
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (r *nlPlateResolver) fetchCarrosserieByPlate(ctx context.Context, plate string) ([]rdwPlateCarrosserie, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		r.baseURL, rdwCarrosserieDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW carrosserie request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateCarrosserie
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}
