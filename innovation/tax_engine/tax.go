package tax

// VATRegime identifies the legal framework governing a cross-border transaction.
type VATRegime string

const (
	RegimeMarginScheme   VATRegime = "MARGIN_SCHEME"
	RegimeIntraCommunity VATRegime = "INTRA_COMMUNITY"
	RegimeExportImport   VATRegime = "EXPORT_IMPORT"
)

// NationalVATRates maps country code → standard VAT rate (decimal).
var NationalVATRates = map[string]float64{
	"DE": 0.19,
	"FR": 0.20,
	"ES": 0.21,
	"BE": 0.21,
	"NL": 0.21,
	"CH": 0.081,
}

// EUCountries is the set of EU member states in the matrix.
var EUCountries = map[string]bool{
	"DE": true, "FR": true, "ES": true, "BE": true, "NL": true,
}

// VATRoute describes a single applicable VAT regime for a country pair.
type VATRoute struct {
	FromCountry string
	ToCountry   string
	Regime      VATRegime
	VATRate     float64
	Conditions  []string
	LegalBasis  string
}

// VATCalculation is a computed route with all monetary amounts in euro cents.
type VATCalculation struct {
	Route        VATRoute
	VehiclePrice int64
	MarginAmount int64
	TaxableBase  int64
	VATAmount    int64
	TotalCost    int64
	NetSaving    int64
	IsOptimal    bool
	Explanation  string
}

// CalculationRequest is the input to Calculate.
type CalculationRequest struct {
	FromCountry       string `json:"from_country"`
	ToCountry         string `json:"to_country"`
	VehiclePriceCents int64  `json:"vehicle_price_cents"`
	MarginCents       int64  `json:"margin_cents"`
	SellerVATID       string `json:"seller_vat_id"`
	BuyerVATID        string `json:"buyer_vat_id"`
	VehicleAgeMonths  int    `json:"vehicle_age_months"`
	VehicleKM         int    `json:"vehicle_km"`
}

// CalculationResponse is the output of Calculate.
type CalculationResponse struct {
	FromCountry  string          `json:"from_country"`
	ToCountry    string          `json:"to_country"`
	VehiclePrice int64           `json:"vehicle_price_cents"`
	IsNewVehicle bool            `json:"is_new_vehicle"`
	VIESStatus   map[string]bool `json:"vies_status"`
	Routes       []VATCalculation
	OptimalRoute *VATCalculation `json:"optimal_route"`
}
