package check

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
)

// VehicleDossier is the complete vehicle autoficha — all data organized into
// semantic sections for direct consumption by a used-car trader.
// Fields are nil/empty when the source country portal does not expose them.
type VehicleDossier struct {
	// Query metadata
	QueryPlate   string    `json:"query_plate"`
	QueryCountry string    `json:"query_country"`
	GeneratedAt  time.Time `json:"generated_at"`

	Identity    DossierIdentity    `json:"identity"`
	Technical   DossierTechnical   `json:"technical"`
	Dimensions  DossierDimensions  `json:"dimensions"`
	Registration DossierRegistration `json:"registration"`
	Ownership   DossierOwnership   `json:"ownership"`
	Legal       DossierLegal       `json:"legal"`
	Safety      DossierSafety      `json:"safety"`
	Inspections DossierInspections `json:"inspections"`
	Fiscal      DossierFiscal      `json:"fiscal"`

	Completeness DossierCompleteness `json:"completeness"`
	DataSources  []DataSource        `json:"data_sources"`
}

// DossierIdentity holds primary identification fields.
type DossierIdentity struct {
	Plate   string `json:"plate,omitempty"`
	VIN     string `json:"vin,omitempty"`
	Make    string `json:"make,omitempty"`
	Model   string `json:"model,omitempty"`
	Variant string `json:"variant,omitempty"`
	Color   string `json:"color,omitempty"`
}

// DossierTechnical holds mechanical and regulatory specs.
type DossierTechnical struct {
	FuelType          string  `json:"fuel_type,omitempty"`
	DisplacementCC    int     `json:"displacement_cc,omitempty"`
	PowerKW           float64 `json:"power_kw,omitempty"`
	PowerCV           int     `json:"power_cv,omitempty"`
	CO2GPerKm         float64 `json:"co2_g_per_km,omitempty"`
	EuroNorm          string  `json:"euro_norm,omitempty"`
	BodyType          string  `json:"body_type,omitempty"`
	Transmission      string  `json:"transmission,omitempty"`
	NumberOfSeats     int     `json:"number_of_seats,omitempty"`
	NumberOfDoors     int     `json:"number_of_doors,omitempty"`
	NumberOfCylinders int     `json:"number_of_cylinders,omitempty"`
	EngineCode        string  `json:"engine_code,omitempty"`
	EnergyLabel       string  `json:"energy_label,omitempty"`

	FuelConsumptionCombinedL100km   float64 `json:"fuel_consumption_combined_l100km,omitempty"`
	FuelConsumptionCityL100km       float64 `json:"fuel_consumption_city_l100km,omitempty"`
	FuelConsumptionExtraUrbanL100km float64 `json:"fuel_consumption_extra_urban_l100km,omitempty"`
}

// DossierDimensions holds physical measurements.
type DossierDimensions struct {
	LengthCm           int `json:"length_cm,omitempty"`
	WidthCm            int `json:"width_cm,omitempty"`
	HeightCm           int `json:"height_cm,omitempty"`
	WheelbaseCm        int `json:"wheelbase_cm,omitempty"`
	CurbWeightKg       int `json:"curb_weight_kg,omitempty"`
	GrossWeightKg      int `json:"gross_weight_kg,omitempty"`
	TechnicalMaxMassKg int `json:"technical_max_mass_kg,omitempty"`
	LoadCapacityKg     int `json:"load_capacity_kg,omitempty"`
	MaxSpeedKmh        int `json:"max_speed_kmh,omitempty"`
}

// DossierRegistration holds registration and administrative data.
type DossierRegistration struct {
	FirstRegistration      *time.Time `json:"first_registration,omitempty"`
	FirstDutchRegistration *time.Time `json:"first_dutch_registration,omitempty"`
	Country                string     `json:"country,omitempty"`
	RegistrationStatus     string     `json:"registration_status,omitempty"`
	EnvironmentalBadge     string     `json:"environmental_badge,omitempty"`
}

// DossierOwnership holds ownership history data.
type DossierOwnership struct {
	TransferCount       int        `json:"transfer_count,omitempty"`
	PreviousOwners      int        `json:"previous_owners,omitempty"`
	LastTransactionDate *time.Time `json:"last_transaction_date,omitempty"`
	ServiceCode         string     `json:"service_code,omitempty"` // B00=private,A04=taxi,...
}

// DossierLegal holds legal and administrative flags.
type DossierLegal struct {
	EmbargoFlag      bool   `json:"embargo_flag,omitempty"`
	StolenFlag       bool   `json:"stolen_flag,omitempty"`
	PrecintedFlag    bool   `json:"precinted_flag,omitempty"`
	RentingFlag      bool   `json:"renting_flag,omitempty"`
	CancellationType string `json:"cancellation_type,omitempty"`
	TempCancelled    bool   `json:"temp_cancelled,omitempty"`
	ExportIndicator  bool   `json:"export_indicator,omitempty"`
	OpenRecall       bool   `json:"open_recall,omitempty"`
	TaxiIndicator    bool   `json:"taxi_indicator,omitempty"`

	// HasAlerts is true when any flag above is set — shortcut for UI.
	HasAlerts bool `json:"has_alerts"`
}

// DossierSafety holds EuroNCAP and RAPEX data.
type DossierSafety struct {
	NCAPStars                 int          `json:"ncap_stars,omitempty"`
	NCAPAdultOccupantPct      float64      `json:"ncap_adult_occupant_pct,omitempty"`
	NCAPChildOccupantPct      float64      `json:"ncap_child_occupant_pct,omitempty"`
	NCAPVulnerableRoadUserPct float64      `json:"ncap_vulnerable_road_user_pct,omitempty"`
	NCAPSafetyAssistPct       float64      `json:"ncap_safety_assist_pct,omitempty"`
	NCAPRatingYear            int          `json:"ncap_rating_year,omitempty"`
	EURAPEXAlerts             []EURAPEXAlert `json:"eu_rapex_alerts,omitempty"`
}

// DossierInspections holds technical inspection history.
type DossierInspections struct {
	LastInspectionDate   *time.Time `json:"last_inspection_date,omitempty"`
	LastInspectionResult string     `json:"last_inspection_result,omitempty"`
	NextInspectionDate   *time.Time `json:"next_inspection_date,omitempty"`
	MileageKm            int        `json:"mileage_km,omitempty"`
	MileageDate          *time.Time `json:"mileage_date,omitempty"`
	OdometerStatus       string     `json:"odometer_status,omitempty"`
	APKHistory           []APKEntry `json:"apk_history,omitempty"`
}

// DossierFiscal holds fiscal/tax data.
type DossierFiscal struct {
	ImportTaxEUR       int    `json:"import_tax_eur,omitempty"`
	CataloguePriceEUR  int    `json:"catalogue_price_eur,omitempty"`
	TypeApprovalNumber string `json:"type_approval_number,omitempty"`
}

// SectionStatus indicates data availability for a section.
type SectionStatus string

const (
	SectionFull        SectionStatus = "full"
	SectionPartial     SectionStatus = "partial"
	SectionUnavailable SectionStatus = "unavailable"
)

// DossierCompleteness reports data availability per section.
type DossierCompleteness struct {
	Identity     SectionStatus `json:"identity"`
	Technical    SectionStatus `json:"technical"`
	Dimensions   SectionStatus `json:"dimensions"`
	Registration SectionStatus `json:"registration"`
	Ownership    SectionStatus `json:"ownership"`
	Legal        SectionStatus `json:"legal"`
	Safety       SectionStatus `json:"safety"`
	Inspections  SectionStatus `json:"inspections"`
	Fiscal       SectionStatus `json:"fiscal"`
}

// dossierFromPlate converts a PlateResult into a structured VehicleDossier.
func dossierFromPlate(p *PlateResult, sources []DataSource) *VehicleDossier {
	d := &VehicleDossier{
		QueryPlate:   p.Plate,
		QueryCountry: p.Country,
		GeneratedAt:  time.Now().UTC(),
		DataSources:  sources,
	}

	d.Identity = DossierIdentity{
		Plate:   p.Plate,
		VIN:     p.VIN,
		Make:    p.Make,
		Model:   p.Model,
		Variant: p.Variant,
		Color:   p.Color,
	}

	d.Technical = DossierTechnical{
		FuelType:                        p.FuelType,
		DisplacementCC:                  p.DisplacementCC,
		PowerKW:                         p.PowerKW,
		PowerCV:                         p.PowerCV,
		CO2GPerKm:                       p.CO2GPerKm,
		EuroNorm:                        p.EuroNorm,
		BodyType:                        p.BodyType,
		Transmission:                    p.Transmission,
		NumberOfSeats:                   p.NumberOfSeats,
		NumberOfDoors:                   p.NumberOfDoors,
		NumberOfCylinders:               p.NumberOfCylinders,
		EngineCode:                      p.EngineCode,
		EnergyLabel:                     p.EnergyLabel,
		FuelConsumptionCombinedL100km:   p.FuelConsumptionCombinedL100km,
		FuelConsumptionCityL100km:       p.FuelConsumptionCityL100km,
		FuelConsumptionExtraUrbanL100km: p.FuelConsumptionExtraUrbanL100km,
	}

	d.Dimensions = DossierDimensions{
		LengthCm:           p.LengthCm,
		WidthCm:            p.WidthCm,
		HeightCm:           p.HeightCm,
		WheelbaseCm:        p.WheelbaseCm,
		CurbWeightKg:       p.CurbWeightKg,
		GrossWeightKg:      p.GrossWeightKg,
		TechnicalMaxMassKg: p.TechnicalMaxMassKg,
		LoadCapacityKg:     p.LoadCapacityKg,
		MaxSpeedKmh:        p.MaxSpeedKmh,
	}

	d.Registration = DossierRegistration{
		FirstRegistration:      p.FirstRegistration,
		FirstDutchRegistration: p.FirstDutchRegistration,
		Country:                p.Country,
		RegistrationStatus:     p.RegistrationStatus,
		EnvironmentalBadge:     p.EnvironmentalBadge,
	}

	d.Ownership = DossierOwnership{
		TransferCount:       p.TransferCount,
		PreviousOwners:      p.PreviousOwners,
		LastTransactionDate: p.LastTransactionDate,
		ServiceCode:         p.ServiceCode,
	}

	legal := DossierLegal{
		EmbargoFlag:      p.EmbargoFlag,
		StolenFlag:       p.StolenFlag,
		PrecintedFlag:    p.PrecintedFlag,
		RentingFlag:      p.RentingFlag,
		CancellationType: p.CancellationType,
		TempCancelled:    p.TempCancelled,
		ExportIndicator:  p.ExportIndicator,
		OpenRecall:       p.OpenRecall,
		TaxiIndicator:    p.TaxiIndicator,
	}
	legal.HasAlerts = p.EmbargoFlag || p.StolenFlag || p.PrecintedFlag ||
		p.OpenRecall || p.ExportIndicator
	d.Legal = legal

	d.Safety = DossierSafety{
		NCAPStars:                 p.NCAPStars,
		NCAPAdultOccupantPct:      p.NCAPAdultOccupantPct,
		NCAPChildOccupantPct:      p.NCAPChildOccupantPct,
		NCAPVulnerableRoadUserPct: p.NCAPVulnerableRoadUserPct,
		NCAPSafetyAssistPct:       p.NCAPSafetyAssistPct,
		NCAPRatingYear:            p.NCAPRatingYear,
		EURAPEXAlerts:             p.EURAPEXAlerts,
	}

	d.Inspections = DossierInspections{
		LastInspectionDate:   p.LastInspectionDate,
		LastInspectionResult: p.LastInspectionResult,
		NextInspectionDate:   p.NextInspectionDate,
		MileageKm:            p.MileageKm,
		MileageDate:          p.MileageDate,
		OdometerStatus:       p.OdometerStatus,
		APKHistory:           p.APKHistory,
	}

	d.Fiscal = DossierFiscal{
		ImportTaxEUR:       p.ImportTaxEUR,
		CataloguePriceEUR:  p.CataloguePriceEUR,
		TypeApprovalNumber: p.TypeApprovalNumber,
	}

	d.Completeness = computeCompleteness(d)
	return d
}

func computeCompleteness(d *VehicleDossier) DossierCompleteness {
	id := &d.Identity
	return DossierCompleteness{
		Identity:     sectionStatus(id.Make != "" && id.Model != "", id.Plate != ""),
		Technical:    sectionStatus(d.Technical.PowerKW > 0 && d.Technical.FuelType != "", d.Technical.DisplacementCC > 0 || d.Technical.FuelType != ""),
		Dimensions:   sectionStatus(d.Dimensions.LengthCm > 0 && d.Dimensions.CurbWeightKg > 0, d.Dimensions.CurbWeightKg > 0 || d.Dimensions.GrossWeightKg > 0),
		Registration: sectionStatus(d.Registration.FirstRegistration != nil && d.Registration.RegistrationStatus != "", d.Registration.FirstRegistration != nil || d.Registration.EnvironmentalBadge != ""),
		Ownership:    sectionStatus(d.Ownership.TransferCount > 0 && d.Ownership.LastTransactionDate != nil, d.Ownership.TransferCount > 0 || d.Ownership.PreviousOwners > 0),
		Legal:        sectionStatus(!d.Legal.HasAlerts && d.Registration.RegistrationStatus != "", d.Registration.RegistrationStatus != "" || d.Ownership.TransferCount > 0),
		Safety:       sectionStatus(d.Safety.NCAPStars > 0 && len(d.Safety.EURAPEXAlerts) >= 0, d.Safety.NCAPStars > 0),
		Inspections:  sectionStatus(d.Inspections.LastInspectionDate != nil && len(d.Inspections.APKHistory) > 0, d.Inspections.LastInspectionDate != nil),
		Fiscal:       sectionStatus(d.Fiscal.ImportTaxEUR > 0, d.Fiscal.CataloguePriceEUR > 0 || d.Fiscal.ImportTaxEUR > 0),
	}
}

// sectionStatus returns full when full==true, partial when partial==true, unavailable otherwise.
func sectionStatus(full, partial bool) SectionStatus {
	if full {
		return SectionFull
	}
	if partial {
		return SectionPartial
	}
	return SectionUnavailable
}

// DossierHandler handles the /api/v1/dossier/{country}/{plate} route.
type DossierHandler struct {
	plates    *PlateRegistry
	anonLimit *RateLimiter
	isValidToken func(string) bool
}

// NewDossierHandler creates the handler.
func NewDossierHandler(plates *PlateRegistry, isValid func(string) bool) *DossierHandler {
	return &DossierHandler{
		plates:       plates,
		anonLimit:    NewRateLimiter(10, time.Hour),
		isValidToken: isValid,
	}
}

// Register mounts the dossier route on mux.
func (h *DossierHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/dossier/{country}/{plate}", h.dossier)
}

func (h *DossierHandler) dossier(w http.ResponseWriter, r *http.Request) {
	country := strings.ToUpper(strings.TrimSpace(r.PathValue("country")))
	plate := strings.TrimSpace(r.PathValue("plate"))
	if country == "" || plate == "" {
		jsonDossierErr(w, http.StatusBadRequest, "country and plate are required")
		return
	}

	// Auth: authenticated users bypass rate limit.
	authenticated := false
	if h.isValidToken != nil {
		if tok := bearerToken(r); tok != "" {
			authenticated = h.isValidToken(tok)
		}
	}
	if !authenticated {
		ip := clientIPCheck(r)
		if !h.anonLimit.Allow(ip) {
			w.Header().Set("Retry-After", "3600")
			jsonDossierErr(w, http.StatusTooManyRequests, "rate limit exceeded — 10 requests per hour")
			return
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	plateResult, err := h.plates.Resolve(ctx, plate, country)
	if err != nil {
		switch {
		case errors.Is(err, ErrPlateCountryNotSupported):
			jsonDossierErr(w, http.StatusServiceUnavailable, "plate lookup unavailable for "+country)
		case errors.Is(err, ErrPlateNotFound):
			jsonDossierErr(w, http.StatusNotFound, "plate not found: "+plate)
		case errors.Is(err, ErrPlateResolutionUnavailable):
			// Return partial dossier with whatever we know (NCAP/RAPEX may still be enriched if make known).
			partial := &PlateResult{
				Plate:     NormalizePlate(plate),
				Country:   country,
				Source:    err.Error(),
				FetchedAt: time.Now().UTC(),
				Partial:   true,
			}
			sources := []DataSource{{
				ID:      "plate-resolver",
				Name:    "No hay fuente pública disponible para " + country,
				Country: country,
				Status:  StatusUnavailable,
			}}
			dossier := dossierFromPlate(partial, sources)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(dossier)
		default:
			jsonDossierErr(w, http.StatusInternalServerError, "dossier generation failed")
		}
		return
	}

	sources := []DataSource{{
		ID:      "plate-resolver",
		Name:    plateResult.Source,
		Country: country,
		Status:  StatusSuccess,
	}}

	dossier := dossierFromPlate(plateResult, sources)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Dossier-Completeness-Identity", string(dossier.Completeness.Identity))
	_ = json.NewEncoder(w).Encode(dossier)
}

func jsonDossierErr(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

// bearerToken extracts the Bearer token from Authorization header.
func bearerToken(r *http.Request) string {
	v := r.Header.Get("Authorization")
	if strings.HasPrefix(v, "Bearer ") {
		return v[7:]
	}
	return ""
}
