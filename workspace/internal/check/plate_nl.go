package check

// NL plate resolver — RDW Open Data (Rijksdienst voor het Wegverkeer)
//
// Source:   opendata.rdw.nl — no API key required.
// Datasets (all Socrata):
//   m9d7-ebf2  Gekentekende voertuigen  — main register
//   8ys7-d773  Brandstof                — fuel type, CO2, consumption, Euro norm
//   sgfe-77wx  APK / MOT inspections    — inspection history + expiry
//   a34c-vvps  Geconstateerde gebreken  — defects per APK inspection
//   3huj-srit  Assen                    — axles
//   vezc-m2t6  Carrosserie              — body type (European classification)
// Rate-limit: ≤1 req/sec per Socrata terms of service.

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
	TweedeKleur                    string `json:"tweede_kleur"`  // secondary colour
	DatumEersteToelating           string `json:"datum_eerste_toelating"`             // YYYYMMDD
	DatumTenaamstelling            string `json:"datum_tenaamstelling"`               // current registration date
	DatumEersteNL                  string `json:"datum_eerste_tenaamstelling_in_nederland"`
	BrandstofOmschrijving          string `json:"brandstof_omschrijving"`
	MassaLeegVoertuig              string `json:"massa_ledig_voertuig"`               // kg
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"`  // kg
	Voertuigsoort                  string `json:"voertuigsoort"`
	CilinderInhoud                 string `json:"cilinderinhoud"`                     // cc
	AantalCilinders                string `json:"aantal_cilinders"`
	AantalZitplaatsen              string `json:"aantal_zitplaatsen"`
	AantalDeuren                   string `json:"aantal_deuren"`
	AantalWielen                   string `json:"aantal_wielen"`
	Wielbasis                      string `json:"wielbasis"` // cm
	VervaldatumAPK                 string `json:"vervaldatum_apk"`                    // YYYYMMDD
	NettoMaximumvermogen           string `json:"netto_maximumvermogen"`              // kW
	CO2UitstootGecombineerd        string `json:"co2_uitstoot_gecombineerd"`          // g/km
	EuroClassificatie              string `json:"uitstoot_deeltjes_licht"`            // Euro norm proxy
	WamVerzekerd                   string `json:"wam_verzekerd"`                      // "Ja"/"Nee"
	TenaamstellenMogelijk          string `json:"tenaamstellen_mogelijk"`
	ExportIndicator                string `json:"export_indicator"`
	OpenstaandeTerugroepActie      string `json:"openstaande_terugroepactie_indicator"`
	TaxiIndicator                  string `json:"taxi_indicator"`
	Tellerstandoordeel             string `json:"tellerstandoordeel"`
	JaarLaatsteRegistratie         string `json:"jaar_laatste_registratie_tellerstand"`
	Variant                        string `json:"variant"`
	Typegoedkeuringsnummer         string `json:"typegoedkeuringsnummer"`
	EuropeseVoertuigcategorie      string `json:"europese_voertuigcategorie"`
	Zuinigheidsclassificatie       string `json:"zuinigheidsclassificatie"`
	Catalogusprijs                 string `json:"catalogusprijs"`
	MaximumMassaTrekkenGeremd      string `json:"maximum_trekken_massa_geremd"`
	MaximumMassaTrekkenOngeremd    string `json:"maximum_massa_trekken_ongeremd"`
}

// rdwPlateAPK captures APK inspection rows from sgfe-77wx.
type rdwPlateAPK struct {
	Kenteken       string `json:"kenteken"`
	MeldDatum      string `json:"meld_datum_door_keuringsinstantie_dt"` // ISO 8601
	SoortErkenning string `json:"soort_erkenning_omschrijving"`
	SoortMelding   string `json:"soort_melding_ki_omschrijving"` // e.g. "periodieke controle"
	Vervaldatum    string `json:"vervaldatum_keuring_dt"`        // ISO 8601
}

// rdwPlateFuel captures fuel/emission rows from the 8ys7-d773 brandstof dataset.
// RDW does NOT include fuel data in the main m9d7-ebf2 dataset; it lives separately.
type rdwPlateFuel struct {
	Kenteken              string `json:"kenteken"`
	BrandstofOmschrijving string `json:"brandstof_omschrijving"`     // e.g. "Benzine"
	Vermogen              string `json:"nettomaximumvermogen"`        // kW
	CO2                   string `json:"co2_uitstoot_gecombineerd"`   // g/km
	EuroNorm              string `json:"uitlaatemissieniveau"`        // e.g. "EURO 6"
	VerbruikGecombineerd  string `json:"brandstofverbruik_gecombineerd"` // L/100km
	VerbruikStad          string `json:"brandstofverbruik_stad"`         // L/100km
	VerbruikBuiten        string `json:"brandstofverbruik_buiten"`       // L/100km
	GeluidStationair      string `json:"geluidsniveau_stationair"`       // dB
	Roetuitstoot          string `json:"roetuitstoot"`                   // g/kWh
	EmissieCode           string `json:"emissiecode_omschrijving"`
}

// rdwPlateDefect captures defect rows from a34c-vvps (one row per defect type found).
type rdwPlateDefect struct {
	Kenteken        string `json:"kenteken"`
	MeldDatum       string `json:"meld_datum_door_keuringsinstantie_dt"`
	AantalGebreken  string `json:"aantal_gebreken_geconstateerd"`
	GebrekIdent     string `json:"gebrek_identificatie"`
}

// rdwPlateAxle captures axle rows from 3huj-srit.
type rdwPlateAxle struct {
	Kenteken    string `json:"kenteken"`
	AsNummer    string `json:"as_nummer"`
	AantalAssen string `json:"aantal_assen"`
}

// rdwPlateBody captures body-type rows from vezc-m2t6.
type rdwPlateBody struct {
	Kenteken            string `json:"kenteken"`
	Carrosserietype     string `json:"carrosserietype"`
	EuropeseOmschrijving string `json:"type_carrosserie_europese_omschrijving"`
}

// RDW Open Data dataset IDs consulted by the plate resolver.
// rdwVehiclesDS/rdwAPKDS/rdwDefectsDS are declared in provider_nl.go.
const (
	rdwFuelDS  = "8ys7-d773" // brandstof
	rdwAxlesDS = "3huj-srit" // assen
	rdwBodyDS  = "vezc-m2t6" // carrosserie
)

func (r *nlPlateResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	// 1. Fetch primary vehicle record by kenteken (required — everything else is best-effort).
	vehicle, err := r.fetchVehicleByPlate(ctx, plate)
	if err != nil {
		return nil, err
	}

	result := &PlateResult{
		Plate:                      plate,
		Make:                       strings.TrimSpace(vehicle.Merk),
		Model:                      strings.TrimSpace(vehicle.Handelsbenaming),
		Variant:                    strings.TrimSpace(vehicle.Variant),
		BodyType:                   strings.TrimSpace(vehicle.Inrichting),
		Color:                      strings.TrimSpace(vehicle.EersteKleur),
		FuelType:                   strings.TrimSpace(vehicle.BrandstofOmschrijving),
		VehicleType:                strings.TrimSpace(vehicle.Voertuigsoort),
		EuropeanVehicleCategory:    strings.TrimSpace(vehicle.EuropeseVoertuigcategorie),
		TypeApprovalNumber:         strings.TrimSpace(vehicle.Typegoedkeuringsnummer),
		EnergyLabel:                strings.TrimSpace(vehicle.Zuinigheidsclassificatie),
		DisplacementCC:             parseInt(vehicle.CilinderInhoud),
		NumberOfCylinders:          parseInt(vehicle.AantalCilinders),
		NumberOfSeats:              parseInt(vehicle.AantalZitplaatsen),
		NumberOfDoors:              parseInt(vehicle.AantalDeuren),
		NumberOfWheels:             parseInt(vehicle.AantalWielen),
		WheelbaseCm:                parseInt(vehicle.Wielbasis),
		EmptyWeightKg:              parseInt(vehicle.MassaLeegVoertuig),
		GrossWeightKg:              parseInt(vehicle.ToegestaneMaximumMassaVoertuig),
		CataloguePriceEUR:          parseInt(vehicle.Catalogusprijs),
		MaxTrailerWeightBrakedKg:   parseInt(vehicle.MaximumMassaTrekkenGeremd),
		MaxTrailerWeightUnbrakedKg: parseInt(vehicle.MaximumMassaTrekkenOngeremd),
		OdometerStatus:             strings.TrimSpace(vehicle.Tellerstandoordeel),
		LastMileageRegistrationYear: parseInt(vehicle.JaarLaatsteRegistratie),
		Country:                    "NL",
		Source:                     "RDW Open Data — m9d7-ebf2 + 8ys7-d773 + sgfe-77wx + a34c-vvps + 3huj-srit + vezc-m2t6",
		FetchedAt:                  time.Now().UTC(),
	}

	// Secondary colour — RDW sentinel "Niet geregistreerd" → treat as empty.
	if c := strings.TrimSpace(vehicle.TweedeKleur); c != "" && !strings.EqualFold(c, "Niet geregistreerd") {
		result.SecondaryColor = c
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
	switch strings.ToLower(strings.TrimSpace(vehicle.WamVerzekerd)) {
	case "ja":
		result.RegistrationStatus = "active"
	case "nee":
		result.RegistrationStatus = "uninsured"
	}
	// Boolean flags — "Ja"/"Nee" sentinels.
	result.ExportIndicator = strings.EqualFold(strings.TrimSpace(vehicle.ExportIndicator), "Ja")
	result.OpenRecall = strings.EqualFold(strings.TrimSpace(vehicle.OpenstaandeTerugroepActie), "Ja")
	result.TaxiIndicator = strings.EqualFold(strings.TrimSpace(vehicle.TaxiIndicator), "Ja")

	// 2. Enrich from secondary datasets concurrently — each failure is non-fatal.
	type fuelOut struct{ v *rdwPlateFuel; err error }
	type apkOut struct{ v []rdwPlateAPK; err error }
	type defectsOut struct{ v []rdwPlateDefect; err error }
	type axlesOut struct{ v []rdwPlateAxle; err error }
	type bodyOut struct{ v *rdwPlateBody; err error }

	var (
		wg       sync.WaitGroup
		fuelRes  fuelOut
		apkRes   apkOut
		defRes   defectsOut
		axleRes  axlesOut
		bodyRes  bodyOut
	)
	wg.Add(5)
	go func() { defer wg.Done(); fuelRes.v, fuelRes.err = r.fetchFuelByPlate(ctx, plate) }()
	go func() { defer wg.Done(); apkRes.v, apkRes.err = r.fetchAPKByPlate(ctx, plate) }()
	go func() { defer wg.Done(); defRes.v, defRes.err = r.fetchDefectsByPlate(ctx, plate) }()
	go func() { defer wg.Done(); axleRes.v, axleRes.err = r.fetchAxlesByPlate(ctx, plate) }()
	go func() { defer wg.Done(); bodyRes.v, bodyRes.err = r.fetchBodyByPlate(ctx, plate) }()
	wg.Wait()

	// Fuel/emission enrichment.
	if fuelRes.err == nil && fuelRes.v != nil {
		fuel := fuelRes.v
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
		result.FuelConsumptionCombinedL100km = parseFloat(fuel.VerbruikGecombineerd)
		result.FuelConsumptionCityL100km = parseFloat(fuel.VerbruikStad)
		result.FuelConsumptionExtraUrbanL100km = parseFloat(fuel.VerbruikBuiten)
		result.StationaryNoiseDb = parseFloat(fuel.GeluidStationair)
		result.SootEmission = parseFloat(fuel.Roetuitstoot)
		if fuel.EmissieCode != "" {
			result.EmissionCode = strings.TrimSpace(fuel.EmissieCode)
		}
	}

	// APK history — build a defect-count index keyed by inspection timestamp,
	// then assemble per-inspection records.
	defectsByDate := map[string]int{} // MeldDatum (ISO) → defect count
	if defRes.err == nil {
		for _, d := range defRes.v {
			if n := parseInt(d.AantalGebreken); n > 0 {
				defectsByDate[d.MeldDatum] = n // same MeldDatum across rows holds the same total
			}
		}
	}
	if apkRes.err == nil && len(apkRes.v) > 0 {
		// Inspections come ordered most-recent first from the query.
		history := make([]APKInspection, 0, len(apkRes.v))
		for _, row := range apkRes.v {
			ins := APKInspection{
				InspectionType: strings.TrimSpace(row.SoortErkenning),
				DefectsFound:   defectsByDate[row.MeldDatum],
			}
			if t := parseRDWDateTime(row.MeldDatum); !t.IsZero() {
				ins.Date = &t
			}
			if t := parseRDWDateTime(row.Vervaldatum); !t.IsZero() {
				ins.ExpiryDate = &t
				ins.Result = "pass"
			} else {
				ins.Result = "pending"
			}
			history = append(history, ins)
		}
		result.APKHistory = history

		latest := apkRes.v[0]
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

	// Axles — the dataset returns one row per axle; count determines total.
	if axleRes.err == nil && len(axleRes.v) > 0 {
		// Prefer the explicit aantal_assen field from any row; fall back to row count.
		if n := parseInt(axleRes.v[0].AantalAssen); n > 0 {
			result.NumberOfAxles = n
		} else {
			result.NumberOfAxles = len(axleRes.v)
		}
	}

	// Body type — RDW carrosserie dataset has the European classification ("Hatchback", "Sedan", etc.)
	// which is more useful than the short code in m9d7-ebf2 (e.g. "hatchback" vs "AB").
	if bodyRes.err == nil && bodyRes.v != nil {
		if eu := strings.TrimSpace(bodyRes.v.EuropeseOmschrijving); eu != "" {
			result.BodyType = eu
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

func (r *nlPlateResolver) fetchDefectsByPlate(ctx context.Context, plate string) ([]rdwPlateDefect, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s&$limit=50",
		r.baseURL, rdwDefectsDS, url.QueryEscape(plate),
	)
	body, status, err := plateGetJSON(ctx, r.client, query)
	if err != nil || status != http.StatusOK {
		return nil, fmt.Errorf("RDW defects request: status=%d err=%v", status, err)
	}
	var rows []rdwPlateDefect
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

func (r *nlPlateResolver) fetchBodyByPlate(ctx context.Context, plate string) (*rdwPlateBody, error) {
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
	if len(rows) == 0 {
		return nil, nil
	}
	return &rows[0], nil
}
