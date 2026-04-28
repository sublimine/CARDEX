package check

import (
	"context"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// ErrPlateResolutionUnavailable is returned when no public portal exists for
// plate→vehicle resolution in the requested country, or when the portal
// requires authentication/payment we cannot satisfy.
var ErrPlateResolutionUnavailable = errors.New("plate resolution unavailable for this country")

// ErrPlateNotFound is returned when a plate is not found in the registry.
var ErrPlateNotFound = errors.New("plate not found")

// PlateResult holds all vehicle information extractable from a public license-plate
// portal. Fields are zero/nil when the source portal does not expose them.
// VIN, Make, Model, and FirstRegistration are the most commonly available;
// remaining fields depend on what each country's portal exposes.
type PlateResult struct {
	// Identification
	VIN     string `json:"vin,omitempty"`
	Plate   string `json:"plate,omitempty"`
	Make    string `json:"make,omitempty"`
	Model   string `json:"model,omitempty"`
	Variant string `json:"variant,omitempty"`

	// Technical
	FuelType          string  `json:"fuel_type,omitempty"`
	DisplacementCC    int     `json:"displacement_cc,omitempty"`
	PowerKW           float64 `json:"power_kw,omitempty"`
	PowerCV           int     `json:"power_cv,omitempty"` // metric horsepower (ES/FR convention)
	EmptyWeightKg     int     `json:"empty_weight_kg,omitempty"`
	GrossWeightKg     int     `json:"gross_weight_kg,omitempty"`
	CO2GPerKm         float64 `json:"co2_g_per_km,omitempty"`
	EuroNorm          string  `json:"euro_norm,omitempty"`
	BodyType          string  `json:"body_type,omitempty"`
	Transmission      string  `json:"transmission,omitempty"` // Manual / Automático / CVT …
	EngineCode        string  `json:"engine_code,omitempty"`  // OEM engine identifier (e.g. CFGB)
	Color             string  `json:"color,omitempty"`
	SecondaryColor    string  `json:"secondary_color,omitempty"`
	NumberOfSeats     int     `json:"number_of_seats,omitempty"`
	NumberOfCylinders int     `json:"number_of_cylinders,omitempty"`
	NumberOfDoors     int     `json:"number_of_doors,omitempty"`
	NumberOfAxles     int     `json:"number_of_axles,omitempty"`
	NumberOfWheels    int     `json:"number_of_wheels,omitempty"`
	WheelbaseCm       int     `json:"wheelbase_cm,omitempty"`
	ModelYear         int     `json:"model_year,omitempty"` // annee_modelo — may differ from first_registration year

	// Fuel consumption (L/100km) — NL RDW brandstof dataset
	FuelConsumptionCombinedL100km   float64 `json:"fuel_consumption_combined_l100km,omitempty"`
	FuelConsumptionCityL100km       float64 `json:"fuel_consumption_city_l100km,omitempty"`
	FuelConsumptionExtraUrbanL100km float64 `json:"fuel_consumption_extra_urban_l100km,omitempty"`

	// Emissions extras
	StationaryNoiseDb float64 `json:"stationary_noise_db,omitempty"`
	SootEmission      float64 `json:"soot_emission,omitempty"`
	EmissionCode      string  `json:"emission_code,omitempty"`

	// Trailer / classification / pricing
	MaxTrailerWeightBrakedKg   int    `json:"max_trailer_weight_braked_kg,omitempty"`
	MaxTrailerWeightUnbrakedKg int    `json:"max_trailer_weight_unbraked_kg,omitempty"`
	EuropeanVehicleCategory    string `json:"european_vehicle_category,omitempty"`
	VehicleType                string `json:"vehicle_type,omitempty"`
	TypeApprovalNumber         string `json:"type_approval_number,omitempty"`
	EnergyLabel                string `json:"energy_label,omitempty"`
	CataloguePriceEUR          int    `json:"catalogue_price_eur,omitempty"`

	// Registration
	FirstRegistration  *time.Time `json:"first_registration,omitempty"`
	Country            string     `json:"country,omitempty"`
	RegistrationStatus string     `json:"registration_status,omitempty"` // active, cancelled, export …

	// Odometer status (NL RDW: tellerstandoordeel)
	OdometerStatus              string `json:"odometer_status,omitempty"` // Logisch, Onlogisch, Geen oordeel
	LastMileageRegistrationYear int    `json:"last_mileage_registration_year,omitempty"`

	// Status flags (NL RDW)
	ExportIndicator bool `json:"export_indicator,omitempty"`
	OpenRecall      bool `json:"open_recall,omitempty"`
	TaxiIndicator   bool `json:"taxi_indicator,omitempty"`

	// Inspection (APK / ITV / CT / TÜV / MFK)
	LastInspectionDate   *time.Time      `json:"last_inspection_date,omitempty"`
	LastInspectionResult string          `json:"last_inspection_result,omitempty"` // pass, fail, pending
	NextInspectionDate   *time.Time      `json:"next_inspection_date,omitempty"`
	APKHistory           []APKEntry      `json:"apk_history,omitempty"`

	// Mileage (exposed by some portals: NL via APK dataset, BE via Car-Pass)
	MileageKm   int        `json:"mileage_km,omitempty"`
	MileageDate *time.Time `json:"mileage_date,omitempty"`

	// Ownership history (ES: comprobarmatricula exposes owner count)
	PreviousOwners int `json:"previous_owners,omitempty"`

	// Geographic context (DE: Zulassungsbezirk; CH: Canton)
	District string `json:"district,omitempty"`

	// Environmental badge (ES: DGT label — Zero / Eco / C / B)
	EnvironmentalBadge string `json:"environmental_badge,omitempty"`

	// Last administrative transaction date (ES: MATRABA FecTramite — most recent transfer/mutation)
	LastTransactionDate *time.Time `json:"last_transaction_date,omitempty"`

	// Last registration date (ES: DGT — when the vehicle was last registered in Spain)
	LastRegistrationDate *time.Time `json:"last_registration_date,omitempty"`
	// RegistrationType (ES: DGT — "Ordinaria", "Baja temporal", etc.)
	RegistrationType string `json:"registration_type,omitempty"`
	// Origin of the vehicle (ES: DGT — "Importación U.E.", "Nacional", "Importación extra-UE")
	Procedencia string `json:"procedencia,omitempty"`
	// VehicleAge as computed by DGT (e.g. "16 años, 8 meses y 2 días")
	VehicleAge string `json:"vehicle_age,omitempty"`

	// Current owner location and tenure (ES: DGT INTV)
	CurrentOwnerMunicipio        string `json:"current_owner_municipio,omitempty"`
	CurrentOwnerProvincia        string `json:"current_owner_provincia,omitempty"`
	CurrentOwnerTimeInPossession string `json:"current_owner_time_in_possession,omitempty"`
	CurrentOwnerPersonType       string `json:"current_owner_person_type,omitempty"`

	// Manufacturer/importer (ES: DGT — may differ from Make when imported via a dealer)
	Manufacturer string `json:"manufacturer,omitempty"`

	// ImportAlert is true when DGT flags the vehicle as imported (affects buyer due-diligence)
	ImportAlert bool `json:"import_alert,omitempty"`

	// DGT MATRABA legal/administrative status flags (ES)
	// Source: DGT microdatos abiertos (matraba) — free, no auth required.
	EmbargoFlag      bool   `json:"embargo_flag,omitempty"`       // IndEmbargo: has active judicial/administrative lien
	PrecintedFlag    bool   `json:"precinted_flag,omitempty"`     // IndPrecinto: vehicle is seized
	StolenFlag       bool   `json:"stolen_flag,omitempty"`        // IndSustraccion: reported stolen
	RentingFlag      bool   `json:"renting_flag,omitempty"`       // Renting: is/was a renting vehicle
	CancellationType string `json:"cancellation_type,omitempty"` // IndBajaDef: 0=active,1=scrapped,2=exported,3=admin baja...
	TempCancelled    bool   `json:"temp_cancelled,omitempty"`     // IndBajaTemp: temporarily off the road
	TransferCount    int    `json:"transfer_count,omitempty"`     // NumTransmisiones: number of ownership changes
	ServiceCode      string `json:"service_code,omitempty"`      // Servicio: B00=private,A04=taxi,A01=driving school,...

	// Dimensions (NL RDW m9d7-ebf2)
	LengthCm int `json:"length_cm,omitempty"`
	WidthCm  int `json:"width_cm,omitempty"`
	HeightCm int `json:"height_cm,omitempty"`

	// Mass and capacity (NL RDW m9d7-ebf2)
	CurbWeightKg       int `json:"curb_weight_kg,omitempty"`        // massa_rijklaar
	TechnicalMaxMassKg int `json:"technical_max_mass_kg,omitempty"` // technische_max_massa_voertuig
	LoadCapacityKg     int `json:"load_capacity_kg,omitempty"`      // laadvermogen

	// Performance (NL RDW m9d7-ebf2)
	MaxSpeedKmh int `json:"max_speed_kmh,omitempty"` // maximale_constructiesnelheid

	// Fiscal (NL RDW m9d7-ebf2 — import tax paid at first Dutch registration)
	ImportTaxEUR int `json:"import_tax_eur,omitempty"` // bruto_bpm

	// Type approval variant/execution codes (NL RDW m9d7-ebf2)
	TypeApprovalVariant   string `json:"type_approval_variant,omitempty"`   // variant code
	TypeApprovalExecution string `json:"type_approval_execution,omitempty"` // uitvoering code

	// NL: first Dutch registration date (may differ from first_registration when imported)
	FirstDutchRegistration *time.Time `json:"first_dutch_registration,omitempty"`

	// EuroNCAP safety rating (model-level, not per-vehicle)
	NCAPStars                 int     `json:"ncap_stars,omitempty"`
	NCAPAdultOccupantPct      float64 `json:"ncap_adult_occupant_pct,omitempty"`
	NCAPChildOccupantPct      float64 `json:"ncap_child_occupant_pct,omitempty"`
	NCAPVulnerableRoadUserPct float64 `json:"ncap_vulnerable_road_user_pct,omitempty"`
	NCAPSafetyAssistPct       float64 `json:"ncap_safety_assist_pct,omitempty"`
	NCAPRatingYear            int     `json:"ncap_rating_year,omitempty"`

	// EU Safety Gate (RAPEX) alerts matching this make/model
	EURAPEXAlerts []EURAPEXAlert `json:"eu_rapex_alerts,omitempty"`

	// Ownership history — full list of owners with dates and location (ES: DGT INTV)
	OwnerHistory []OwnerEntry `json:"owner_history,omitempty"`

	// Movement history — matriculaciones, transferencias, bajas (ES: DGT INTV)
	MovementHistory []MovementEntry `json:"movement_history,omitempty"`

	// Metadata
	Source    string    `json:"source"`
	FetchedAt time.Time `json:"fetched_at"`
	Partial   bool      `json:"partial,omitempty"` // true when only a subset of fields is available
}

// OwnerEntry is a single ownership period for a vehicle.
type OwnerEntry struct {
	Date             *time.Time `json:"date,omitempty"`
	Municipio        string     `json:"municipio,omitempty"`
	Provincia        string     `json:"provincia,omitempty"`
	TimeInPossession string     `json:"time_in_possession,omitempty"`
	PersonType       string     `json:"person_type,omitempty"` // Física / Jurídica
	ServiceCode      string     `json:"service_code,omitempty"`
}

// MovementEntry is a single administrative event (matriculación, transferencia, baja).
type MovementEntry struct {
	Type      string     `json:"type"`             // "Matriculación ordinaria", "Transferencia", "Baja"…
	Date      *time.Time `json:"date,omitempty"`
	Municipio string     `json:"municipio,omitempty"`
	Provincia string     `json:"provincia,omitempty"`
	Duration  string     `json:"duration,omitempty"`
}

// APKDefect is a single defect found during an APK (MOT) inspection.
type APKDefect struct {
	Code    string `json:"code"`
	Count   int    `json:"count"`
	Station string `json:"station,omitempty"`
}

// APKEntry is one APK inspection record — combined view from NL RDW
// sgfe-77wx (dates/results/type) and a34c-vvps (defect codes/counts).
type APKEntry struct {
	Date           time.Time   `json:"date"`
	Result         string      `json:"result"` // "pass", "fail", "pending", "advisory"
	Station        string      `json:"station,omitempty"`
	NextDueDate    *time.Time  `json:"next_due,omitempty"`
	ExpiryDate     *time.Time  `json:"expiry_date,omitempty"`
	InspectionType string      `json:"inspection_type,omitempty"` // e.g. "APK Lichte voertuigen"
	DefectsFound   int         `json:"defects_found,omitempty"`
	Defects        []APKDefect `json:"defects,omitempty"`
}

// PlateResolver converts a normalised license plate into a PlateResult.
// The country is embedded in the resolver implementation.
type PlateResolver interface {
	Resolve(ctx context.Context, plate string) (*PlateResult, error)
}

// NormalizePlate strips whitespace and dashes then uppercases.
// "1-ABC-23" → "1ABC23", "ab 12 cd" → "AB12CD".
func NormalizePlate(plate string) string {
	plate = strings.ToUpper(plate)
	plate = strings.ReplaceAll(plate, " ", "")
	plate = strings.ReplaceAll(plate, "-", "")
	return plate
}

// PlateRegistry maps ISO-3166-1 alpha-2 country codes to PlateResolver implementations.
// After plate resolution it enriches the result with EuroNCAP safety ratings and
// EU Safety Gate (RAPEX) recall alerts — both model-level, not per-VIN.
type PlateRegistry struct {
	resolvers map[string]PlateResolver
	ncap      *NCAPResolver
	rapex     *RAPEXResolver
}

// NewPlateRegistry builds the production registry.
// rdwBaseURL is the RDW Open Data resource base, e.g. "https://opendata.rdw.nl/resource".
func NewPlateRegistry(rdwBaseURL string) *PlateRegistry {
	return NewPlateRegistryWithCache(rdwBaseURL, nil)
}

// NewPlateRegistryWithCache builds the production registry with an optional
// persistent cache. Currently consumed by the ES resolver to survive
// comprobarmatricula.com rate-limits; other resolvers may adopt it later.
func NewPlateRegistryWithCache(rdwBaseURL string, cache *Cache) *PlateRegistry {
	return NewPlateRegistryWithOptions(rdwBaseURL, cache, nil, "")
}

// NewPlateRegistryWithOptions is the most-configurable constructor.
// cmProxyURL: when non-empty, ES plate lookups route through the Vercel edge
// proxy (different IP per call → permanent elimination of CM rate limits).
//
// Optional env vars for unlocking additional country data:
//   CH_PLATE_API_KEY — kennzeichenapi.ch username (register free at kennzeichenapi.ch)
//   DE_PLATE_API_KEY — CarsXE API key (trial at carsxe.com, ~$0.05/query)
func NewPlateRegistryWithOptions(rdwBaseURL string, cache *Cache, matrabaStore matrabaLookup, cmProxyURL string) *PlateRegistry {
	client := newPlateHTTPClient(15 * time.Second)
	es := newESPlateResolver(client)
	if cache != nil {
		es = es.WithCache(cache)
	}
	if cmProxyURL != "" {
		es = es.WithProxy(cmProxyURL)
	}
	if matrabaStore != nil {
		es = es.WithMATRABA(matrabaStore)
	}

	// CH: kennzeichenapi.ch when CH_PLATE_API_KEY is set; otherwise canton-only.
	var chResolver PlateResolver = newCHPlateResolver(client)
	if chKey := os.Getenv("CH_PLATE_API_KEY"); chKey != "" {
		chResolver = newCHAPIResolver(client, chKey)
	}

	// DE: CarsXE when DE_PLATE_API_KEY is set; otherwise district-only.
	var deResolver PlateResolver = newDEPlateResolver()
	if deKey := os.Getenv("DE_PLATE_API_KEY"); deKey != "" {
		deResolver = newDEAPIResolver(client, deKey)
	}

	return &PlateRegistry{
		resolvers: map[string]PlateResolver{
			"NL": newNLPlateResolver(client, rdwBaseURL),
			"ES": es,
			"FR": newFRPlateResolver(client),
			"BE": newBEPlateResolver(client),
			"DE": deResolver,
			"CH": chResolver,
		},
		ncap:  NewNCAPResolver(),
		rapex: NewRAPEXResolver(),
	}
}

// NewPlateRegistryFromMap builds a registry from an explicit resolver map (for tests).
func NewPlateRegistryFromMap(resolvers map[string]PlateResolver) *PlateRegistry {
	return &PlateRegistry{resolvers: resolvers}
}

// ErrPlateCountryNotSupported is returned when the country code is not
// recognised by CARDEX at all (as opposed to recognised but with no
// public data source available).
var ErrPlateCountryNotSupported = errors.New("country not supported by CARDEX plate resolver")

// Resolve normalises plate, delegates to the country resolver, then enriches
// the result in parallel with EuroNCAP safety ratings and EU RAPEX alerts.
// Enrichment failures are non-fatal — they leave the NCAP/RAPEX fields empty.
func (r *PlateRegistry) Resolve(ctx context.Context, plate, country string) (*PlateResult, error) {
	resolver, ok := r.resolvers[strings.ToUpper(country)]
	if !ok {
		return nil, ErrPlateCountryNotSupported
	}
	result, err := resolver.Resolve(ctx, NormalizePlate(plate))
	if err != nil {
		return nil, err
	}

	// Enrich with model-level data in parallel when make+model are available.
	if result.Make != "" && result.Model != "" {
		var wg sync.WaitGroup
		wg.Add(2)

		go func() {
			defer wg.Done()
			if r.ncap == nil {
				return
			}
			if ncapRes, e := r.ncap.Resolve(ctx, result.Make, result.Model); e == nil && ncapRes != nil {
				result.NCAPStars = ncapRes.Stars
				result.NCAPAdultOccupantPct = ncapRes.AdultOccupantPct
				result.NCAPChildOccupantPct = ncapRes.ChildOccupantPct
				result.NCAPVulnerableRoadUserPct = ncapRes.VulnerableRoadUserPct
				result.NCAPSafetyAssistPct = ncapRes.SafetyAssistPct
				result.NCAPRatingYear = ncapRes.RatingYear
			}
		}()

		go func() {
			defer wg.Done()
			if r.rapex == nil {
				return
			}
			if alerts, e := r.rapex.Resolve(ctx, result.Make, result.Model); e == nil && len(alerts) > 0 {
				result.EURAPEXAlerts = alerts
				result.OpenRecall = true // escalate: at least one EU-wide alert
			}
		}()

		wg.Wait()
	}

	return result, nil
}

// ── shared HTTP helpers ───────────────────────────────────────────────────────

// plateUA mimics a real browser to avoid trivial bot-detection on government portals.
const plateUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

func newPlateHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{Timeout: timeout}
}

// plateGetHTML sends a GET with browser-like headers; returns body + HTTP status.
func plateGetHTML(ctx context.Context, client *http.Client, rawURL string) ([]byte, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "es-ES,es;q=0.9,fr-FR;q=0.8,nl;q=0.7,de;q=0.6,en;q=0.5")

	resp, err := client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024)) // 512 KB cap
	return body, resp.StatusCode, err
}

// plateGetJSON sends a GET requesting JSON; returns body + HTTP status.
func plateGetJSON(ctx context.Context, client *http.Client, rawURL string) ([]byte, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	return body, resp.StatusCode, err
}

// plateRetry executes fn up to 1+maxRetries times with exponential backoff (300 ms base).
// Retries only on transient failures (HTTP 429/5xx or network errors).
func plateRetry(ctx context.Context, maxRetries int, fn func() ([]byte, int, error)) ([]byte, int, error) {
	var body []byte
	var status int
	var err error
	for i := 0; i <= maxRetries; i++ {
		if i > 0 {
			wait := time.Duration(math.Pow(2, float64(i-1))*300) * time.Millisecond
			select {
			case <-ctx.Done():
				return nil, 0, ctx.Err()
			case <-time.After(wait):
			}
		}
		body, status, err = fn()
		if err == nil && status != http.StatusTooManyRequests && status < 500 {
			return body, status, nil
		}
	}
	return body, status, err
}

// parseFloat converts a string to float64; returns 0 on failure.
func parseFloat(s string) float64 {
	var f float64
	fmt.Sscanf(strings.TrimSpace(s), "%f", &f)
	return f
}

// htmlExtract returns the trimmed text content between two literal string markers.
// Returns "" when start or end is not found.
func htmlExtract(body, start, end string) string {
	i := strings.Index(body, start)
	if i < 0 {
		return ""
	}
	i += len(start)
	j := strings.Index(body[i:], end)
	if j < 0 {
		return ""
	}
	return strings.TrimSpace(body[i : i+j])
}

// htmlExtractAfter locates `after` in body then returns htmlExtract(…, open, close)
// on the suffix that follows it.
func htmlExtractAfter(body, after, open, close string) string {
	i := strings.Index(body, after)
	if i < 0 {
		return ""
	}
	return htmlExtract(body[i+len(after):], open, close)
}

// stripHTMLTags removes any content wrapped in < > from s.
func stripHTMLTags(s string) string {
	var b strings.Builder
	inTag := false
	for _, r := range s {
		switch {
		case r == '<':
			inTag = true
		case r == '>':
			inTag = false
		case !inTag:
			b.WriteRune(r)
		}
	}
	return strings.TrimSpace(b.String())
}
