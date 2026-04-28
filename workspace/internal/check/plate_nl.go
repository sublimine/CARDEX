package check

// NL plate resolver — RDW Open Data (Rijksdienst voor het Wegverkeer).
//
// Source:  opendata.rdw.nl — Socrata, no API key required.
// Datasets consulted in parallel (rate limit ≤1 req/sec per ToS; 6 in-flight
// requests against the public endpoint are within budget):
//
//   m9d7-ebf2  Gekentekende voertuigen — main register (VIN, merk, colour,
//                                        doors, weight, insurance, export flag,
//                                        open-recall, taxi, tellerstandoordeel…)
//   8ys7-d773  Brandstof               — fuel type, Euro norm, CO2, consumption
//   sgfe-77wx  APK / MOT inspections   — history + next-due date
//   a34c-vvps  Geconstateerde gebreken — defect rows per inspection
//   3huj-srit  Assen                   — axle count
//   vezc-m2t6  Carrosserie             — EU body-type classification

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

// Dataset IDs for the secondary (non-vehicle) RDW resources.
// rdwVehiclesDS / rdwAPKDS / rdwDefectsDS are declared in provider_nl.go and
// shared across the package to keep Socrata IDs in one place.
const (
	rdwFuelDS  = "8ys7-d773" // brandstof
	rdwAxlesDS = "3huj-srit" // assen
	rdwBodyDS  = "vezc-m2t6" // carrosserie
)

// nlPlateResolver is the concrete NL resolver.
type nlPlateResolver struct {
	client  *http.Client
	baseURL string // e.g. "https://opendata.rdw.nl/resource"
}

func newNLPlateResolver(client *http.Client, baseURL string) *nlPlateResolver {
	return &nlPlateResolver{client: client, baseURL: baseURL}
}

// NewNLPlateResolverWithBase creates an NL resolver at a custom base URL (tests).
func NewNLPlateResolverWithBase(baseURL string) *nlPlateResolver {
	return &nlPlateResolver{
		client:  newPlateHTTPClient(5 * time.Second),
		baseURL: baseURL,
	}
}

// ── dataset row types ─────────────────────────────────────────────────────────

// rdwPlateVehicle captures the m9d7-ebf2 fields retrievable by kenteken.
type rdwPlateVehicle struct {
	Kenteken                       string `json:"kenteken"`
	VIN                            string `json:"voertuigidentificatienummer"`
	Merk                           string `json:"merk"`
	Handelsbenaming                string `json:"handelsbenaming"`
	Variant                        string `json:"variant"`
	Inrichting                     string `json:"inrichting"`
	EersteKleur                    string `json:"eerste_kleur"`
	TweedeKleur                    string `json:"tweede_kleur"`
	DatumEersteToelating           string `json:"datum_eerste_toelating"`
	DatumTenaamstelling            string `json:"datum_tenaamstelling"`
	BrandstofOmschrijving          string `json:"brandstof_omschrijving"`
	MassaLeegVoertuig              string `json:"massa_ledig_voertuig"`
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"`
	MaximumMassaTrekkenGeremd      string `json:"maximum_trekken_massa_geremd"`
	MaximumMassaTrekkenOngeremd    string `json:"maximum_massa_trekken_ongeremd"`
	Voertuigsoort                  string `json:"voertuigsoort"`
	CilinderInhoud                 string `json:"cilinderinhoud"`
	AantalCilinders                string `json:"aantal_cilinders"`
	AantalZitplaatsen              string `json:"aantal_zitplaatsen"`
	AantalDeuren                   string `json:"aantal_deuren"`
	AantalWielen                   string `json:"aantal_wielen"`
	Wielbasis                      string `json:"wielbasis"`
	VervaldatumAPK                 string `json:"vervaldatum_apk"`
	VervaldatumAPKDT               string `json:"vervaldatum_apk_dt"`
	NettoMaximumvermogen           string `json:"netto_maximumvermogen"`
	CO2UitstootGecombineerd        string `json:"co2_uitstoot_gecombineerd"`
	WamVerzekerd                   string `json:"wam_verzekerd"`
	TenaamstellenMogelijk          string `json:"tenaamstellen_mogelijk"`
	ExportIndicator                string `json:"export_indicator"`
	OpenstaandeTerugroepActie      string `json:"openstaande_terugroepactie_indicator"`
	TaxiIndicator                  string `json:"taxi_indicator"`
	Tellerstandoordeel             string `json:"tellerstandoordeel"`
	JaarLaatsteRegistratie         string `json:"jaar_laatste_registratie_tellerstand"`
	Typegoedkeuringsnummer         string `json:"typegoedkeuringsnummer"`
	EuropeseVoertuigcategorie      string `json:"europese_voertuigcategorie"`
	Zuinigheidsclassificatie       string `json:"zuinigheidsclassificatie"`
	Catalogusprijs                 string `json:"catalogusprijs"`
	// Extended fields — dimensions, mass, performance, fiscal
	Lengte                      string `json:"lengte"`                                    // vehicle length in cm
	Breedte                     string `json:"breedte"`                                   // vehicle width in cm
	HoogteVoertuig              string `json:"hoogte_voertuig"`                           // vehicle height in cm
	MassaRijklaar               string `json:"massa_rijklaar"`                            // curb/ready-to-drive mass kg
	TechnischeMaxMassaVoertuig  string `json:"technische_max_massa_voertuig"`             // technical max mass kg
	Laadvermogen                string `json:"laadvermogen"`                              // load capacity kg
	MaximaleConstructiesnelheid string `json:"maximale_constructiesnelheid"`              // max construction speed km/h
	BrutoBPM                    string `json:"bruto_bpm"`                                 // import tax EUR
	Uitvoering                  string `json:"uitvoering"`                                // type approval execution code
	DatumEersteTenaamstellingNL string `json:"datum_eerste_tenaamstelling_in_nederland"`  // first Dutch registration
}

// rdwPlateFuel captures 8ys7-d773 fuel/emission rows.
type rdwPlateFuel struct {
	Kenteken              string `json:"kenteken"`
	BrandstofOmschrijving string `json:"brandstof_omschrijving"`
	Vermogen              string `json:"nettomaximumvermogen"`
	CO2                   string `json:"co2_uitstoot_gecombineerd"`
	EuroNorm              string `json:"uitlaatemissieniveau"`
	VerbruikGecombineerd  string `json:"brandstofverbruik_gecombineerd"`
	VerbruikStad          string `json:"brandstofverbruik_stad"`
	VerbruikBuiten        string `json:"brandstofverbruik_buiten"`
	GeluidStationair      string `json:"geluidsniveau_stationair"`
	Roetuitstoot          string `json:"roetuitstoot"`
	EmissieCode           string `json:"emissiecode_omschrijving"`
}

// rdwPlateAxle captures 3huj-srit axle rows; one row per axle.
type rdwPlateAxle struct {
	Kenteken       string `json:"kenteken"`
	AsNummer       string `json:"as_nummer"`
	AantalAssen    string `json:"aantal_assen"`
	Spoorbreedte   string `json:"spoorbreedte"`
	MaximaleLastAs string `json:"maximale_last_as"`
}

// rdwPlateBody captures vezc-m2t6 EU body-type rows.
type rdwPlateBody struct {
	Kenteken             string `json:"kenteken"`
	Carrosserietype      string `json:"carrosserietype"`
	EuropeseOmschrijving string `json:"type_carrosserie_europese_omschrijving"`
}

// ── resolver ──────────────────────────────────────────────────────────────────

func (r *nlPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	// 1. Primary fetch — required; all others are best-effort enrichment.
	vehicle, err := r.fetchVehicleByPlate(ctx, plate)
	if err != nil {
		return nil, err
	}

	result := &PlateResult{
		Plate:                       plate,
		Make:                        strings.TrimSpace(vehicle.Merk),
		Model:                       strings.TrimSpace(vehicle.Handelsbenaming),
		Variant:                     strings.TrimSpace(vehicle.Variant),
		BodyType:                    strings.TrimSpace(vehicle.Inrichting),
		Color:                       strings.TrimSpace(vehicle.EersteKleur),
		FuelType:                    strings.TrimSpace(vehicle.BrandstofOmschrijving),
		VehicleType:                 strings.TrimSpace(vehicle.Voertuigsoort),
		EuropeanVehicleCategory:     strings.TrimSpace(vehicle.EuropeseVoertuigcategorie),
		TypeApprovalNumber:          strings.TrimSpace(vehicle.Typegoedkeuringsnummer),
		EnergyLabel:                 strings.TrimSpace(vehicle.Zuinigheidsclassificatie),
		DisplacementCC:              parseInt(vehicle.CilinderInhoud),
		NumberOfCylinders:           parseInt(vehicle.AantalCilinders),
		NumberOfSeats:               parseInt(vehicle.AantalZitplaatsen),
		NumberOfDoors:               parseInt(vehicle.AantalDeuren),
		NumberOfWheels:              parseInt(vehicle.AantalWielen),
		WheelbaseCm:                 parseInt(vehicle.Wielbasis),
		EmptyWeightKg:               parseInt(vehicle.MassaLeegVoertuig),
		GrossWeightKg:               parseInt(vehicle.ToegestaneMaximumMassaVoertuig),
		CataloguePriceEUR:           parseInt(vehicle.Catalogusprijs),
		MaxTrailerWeightBrakedKg:    parseInt(vehicle.MaximumMassaTrekkenGeremd),
		MaxTrailerWeightUnbrakedKg:  parseInt(vehicle.MaximumMassaTrekkenOngeremd),
		OdometerStatus:              strings.TrimSpace(vehicle.Tellerstandoordeel),
		LastMileageRegistrationYear: parseInt(vehicle.JaarLaatsteRegistratie),
		// Extended fields
		LengthCm:              parseInt(vehicle.Lengte),
		WidthCm:               parseInt(vehicle.Breedte),
		HeightCm:              parseInt(vehicle.HoogteVoertuig),
		CurbWeightKg:          parseInt(vehicle.MassaRijklaar),
		TechnicalMaxMassKg:    parseInt(vehicle.TechnischeMaxMassaVoertuig),
		LoadCapacityKg:        parseInt(vehicle.Laadvermogen),
		MaxSpeedKmh:           parseInt(vehicle.MaximaleConstructiesnelheid),
		ImportTaxEUR:          parseInt(vehicle.BrutoBPM),
		TypeApprovalExecution: strings.TrimSpace(vehicle.Uitvoering),
		TypeApprovalVariant:   strings.TrimSpace(vehicle.Variant),
		Country:               "NL",
		Source:                "RDW Open Data — m9d7-ebf2 + 8ys7-d773 + sgfe-77wx + a34c-vvps + 3huj-srit + vezc-m2t6",
		FetchedAt:             time.Now().UTC(),
	}
	if t := parseRDWDate(vehicle.DatumEersteTenaamstellingNL); !t.IsZero() {
		result.FirstDutchRegistration = &t
	}

	// Secondary colour — RDW sentinel "Niet geregistreerd" → treat as empty.
	if c := strings.TrimSpace(vehicle.TweedeKleur); c != "" && !strings.EqualFold(c, "Niet geregistreerd") {
		result.SecondaryColor = c
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
	// APK expiry on vehicle row: prefer ISO datetime, fall back to date-only.
	if t := parseRDWDateTime(vehicle.VervaldatumAPKDT); !t.IsZero() {
		result.NextInspectionDate = &t
	} else if t := parseRDWDate(vehicle.VervaldatumAPK); !t.IsZero() {
		result.NextInspectionDate = &t
	}
	switch strings.ToLower(strings.TrimSpace(vehicle.WamVerzekerd)) {
	case "ja":
		result.RegistrationStatus = "active"
	case "nee":
		result.RegistrationStatus = "uninsured"
	}
	result.ExportIndicator = strings.EqualFold(strings.TrimSpace(vehicle.ExportIndicator), "Ja")
	result.OpenRecall = strings.EqualFold(strings.TrimSpace(vehicle.OpenstaandeTerugroepActie), "Ja")
	result.TaxiIndicator = strings.EqualFold(strings.TrimSpace(vehicle.TaxiIndicator), "Ja")

	// 2. Parallel enrichment — each failure is non-fatal.
	var (
		wg         sync.WaitGroup
		mu         sync.Mutex
		fuelRows   []rdwPlateFuel
		apkRows    []rdwAPK
		defectRows []rdwDefect
		axleRows   []rdwPlateAxle
		bodyRows   []rdwPlateBody
	)
	wg.Add(5)
	go func() {
		defer wg.Done()
		if rows, e := r.fetchFuelRows(ctx, plate); e == nil {
			mu.Lock()
			fuelRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		if rows, e := r.fetchAPKByPlate(ctx, plate); e == nil {
			mu.Lock()
			apkRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		if rows, e := r.fetchDefectsByPlate(ctx, plate); e == nil {
			mu.Lock()
			defectRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		if rows, e := r.fetchAxlesByPlate(ctx, plate); e == nil {
			mu.Lock()
			axleRows = rows
			mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		if rows, e := r.fetchBodyByPlate(ctx, plate); e == nil {
			mu.Lock()
			bodyRows = rows
			mu.Unlock()
		}
	}()
	wg.Wait()

	// Fuel / emission enrichment.
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
		result.FuelConsumptionCombinedL100km = parseFloat(f.VerbruikGecombineerd)
		result.FuelConsumptionCityL100km = parseFloat(f.VerbruikStad)
		result.FuelConsumptionExtraUrbanL100km = parseFloat(f.VerbruikBuiten)
		result.StationaryNoiseDb = parseFloat(f.GeluidStationair)
		result.SootEmission = parseFloat(f.Roetuitstoot)
		if f.EmissieCode != "" {
			result.EmissionCode = strings.TrimSpace(f.EmissieCode)
		}
	}

	// Axles — prefer the explicit aantal_assen field when present; fall back
	// to row count only when the first row carries a valid axle number (guards
	// against a test server echoing unrelated JSON on this endpoint).
	if len(axleRows) > 0 && strings.TrimSpace(axleRows[0].AsNummer) != "" {
		if n := parseInt(axleRows[0].AantalAssen); n > 0 {
			result.NumberOfAxles = n
		} else {
			result.NumberOfAxles = len(axleRows)
		}
	}

	// Body — prefer the European classification when available.
	if len(bodyRows) > 0 {
		if eu := strings.TrimSpace(bodyRows[0].EuropeseOmschrijving); eu != "" {
			result.BodyType = eu
		}
	}

	// APK history — build defect index per inspection date, then assemble
	// per-inspection records.
	if len(apkRows) > 0 {
		// defectsByDate → list of individual defect codes/counts per MeldDatum.
		// defectCountByDate → total defect count per MeldDatum.
		defectsByDate := make(map[string][]APKDefect)
		defectCountByDate := make(map[string]int)
		for _, d := range defectRows {
			count := parseInt(d.AantalGebreken)
			if count == 0 {
				count = 1
			}
			defectCountByDate[d.MeldDatum] = count
			if code := strings.TrimSpace(d.GebrekID); code != "" {
				defectsByDate[d.MeldDatum] = append(defectsByDate[d.MeldDatum], APKDefect{
					Code:    code,
					Count:   count,
					Station: strings.TrimSpace(d.SoortErkenning),
				})
			}
		}

		for _, row := range apkRows {
			entry := APKEntry{
				Station:        strings.TrimSpace(row.SoortErkenning),
				InspectionType: strings.TrimSpace(row.SoortErkenning),
				Defects:        defectsByDate[row.MeldDatum],
				DefectsFound:   defectCountByDate[row.MeldDatum],
			}
			if t := parseRDWDateTime(row.MeldDatum); !t.IsZero() {
				entry.Date = t
			}
			// Result derivation:
			//   Vervaldatum set  → pass (new next-due issued; defects, if any,
			//                      were resolved during this inspection cycle)
			//   defects present  → fail
			//   otherwise        → pending
			if t := parseRDWDateTime(row.Vervaldatum); !t.IsZero() {
				entry.NextDueDate = &t
				entry.ExpiryDate = &t
				entry.Result = "pass"
			} else if entry.DefectsFound > 0 {
				entry.Result = "fail"
			} else {
				entry.Result = "pending"
			}
			result.APKHistory = append(result.APKHistory, entry)
		}

		// Summary fields from the most-recent record (index 0 = DESC order).
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

func (r *nlPlateResolver) fetchAPKByPlate(ctx context.Context, plate string) ([]rdwAPK, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$order=meld_datum_door_keuringsinstantie_dt+DESC&$limit=10",
		r.baseURL, rdwAPKDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW APK request: status=%d err=%v", status, err)
	}
	var rows []rdwAPK
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (r *nlPlateResolver) fetchFuelRows(ctx context.Context, plate string) ([]rdwPlateFuel, error) {
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
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=10",
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

func (r *nlPlateResolver) fetchBodyByPlate(ctx context.Context, plate string) ([]rdwPlateBody, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=1",
		r.baseURL, rdwBodyDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW body request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateBody
	if err := json.Unmarshal(body, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}
