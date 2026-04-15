// Package pipeline defines the core types and interfaces for the extraction
// pipeline. All extraction strategies E01-E12 operate on these types.
package pipeline

import "time"

// Dealer is the input to the extraction pipeline, populated from the discovery
// knowledge graph (dealer_entity + dealer_web_presence + CMS/DMS signals from
// Familia D and Familia E).
type Dealer struct {
	ID              string
	Domain          string
	URLRoot         string
	CountryCode     string   // ISO-3166-1: DE|FR|ES|BE|NL|CH
	PlatformType    string   // "CMS_WORDPRESS"|"CMS_SHOPIFY"|"DMS_HOSTED"|"NATIVE"|"UNKNOWN"
	CMSDetected     string   // CMS/theme fingerprinted by Familia D
	DMSProvider     string   // DMS hosting provider from Familia E (e.g. "dealersocket")
	ExtractionHints []string // signals from Familia D: "schema_org_detected", "wp_car_manager", etc.
	RobotsTxtURL    string
	SitemapURL      string
	RSSFeedURL      string
}

// VehicleRaw contains all fields of a vehicle in raw post-extraction format,
// before normalisation by the quality pipeline. All fields are pointers to
// distinguish "absent" from "zero/empty".
type VehicleRaw struct {
	// Facts — non-copyrightable, basis of the index-pointer model.
	VIN          *string
	Make         *string
	Model        *string
	Year         *int
	Mileage      *int    // km
	FuelType     *string // "gasoline"|"diesel"|"hybrid"|"electric"|"lpg"|"cng"|"hydrogen"
	Transmission *string // "manual"|"automatic"|"semi-automatic"
	PowerKW      *int
	BodyType     *string // "sedan"|"hatchback"|"suv"|"estate"|"coupe"|"convertible"|"van"|"pickup"
	Color        *string
	Doors        *int
	Seats        *int

	// Price — in original currency; EUR conversion happens in normalisation.
	PriceNet   *float64
	PriceGross *float64
	Currency   *string // ISO 4217
	VATMode    *string // "net"|"gross"|"unknown"

	// Pointers (index model — images and descriptions are never copied).
	SourceURL       string   // canonical listing URL on the dealer site
	SourceListingID string   // platform-internal listing ID
	ImageURLs       []string // URL pointers — never stored locally

	// Equipment and extras.
	Equipment        []string               // controlled vocabulary, normalised post-extraction
	AdditionalFields map[string]interface{} // strategy-specific extra data, not yet normalised
}

// IsCritical returns true when all critical fields for a FullSuccess are present.
func (v *VehicleRaw) IsCritical() bool {
	return v.Make != nil && *v.Make != "" &&
		v.Model != nil && *v.Model != "" &&
		v.Year != nil && *v.Year > 0 &&
		(v.PriceNet != nil || v.PriceGross != nil) &&
		v.SourceURL != "" &&
		len(v.ImageURLs) > 0
}

// ExtractionResult encapsulates the outcome of a single strategy run.
type ExtractionResult struct {
	DealerID string
	Strategy string // ExtractionStrategy.ID() that produced this result

	// Vehicles contains the extracted vehicles in raw format.
	Vehicles []*VehicleRaw

	// FullSuccess: >80% of vehicles have all critical fields.
	FullSuccess bool
	// PartialSuccess: some vehicles extracted but critical fields missing on some.
	PartialSuccess bool

	// FieldsExtracted lists field names present on at least one vehicle.
	FieldsExtracted []string
	// FieldsMissing lists critical fields missing across extracted vehicles.
	FieldsMissing []string

	// NextFallback, if not nil, suggests the next strategy ID to try.
	NextFallback *string

	ExtractedAt time.Time
	SourceURL   string
	SourceCount int // number of pages / endpoints consulted

	// Errors contains non-fatal errors encountered during extraction.
	Errors []ExtractionError
}

// ExtractionError captures a non-fatal error with diagnostic context.
type ExtractionError struct {
	Code    string // "HTTP_403"|"ROBOTS_DISALLOW"|"PARSE_ERROR"|"TIMEOUT"|"HTTP_429"
	Message string
	URL     string
	Fatal   bool
}

// CriticalFields is the set of VehicleRaw fields required for FullSuccess.
var CriticalFields = []string{"Make", "Model", "Year", "PriceNet or PriceGross", "SourceURL", "ImageURLs"}

// classifyResult sets FullSuccess / PartialSuccess based on vehicle quality.
func classifyResult(r *ExtractionResult) {
	if len(r.Vehicles) == 0 {
		return
	}
	critical := 0
	for _, v := range r.Vehicles {
		if v.IsCritical() {
			critical++
		}
	}
	ratio := float64(critical) / float64(len(r.Vehicles))
	if ratio >= 0.8 {
		r.FullSuccess = true
		r.PartialSuccess = true
	} else if critical > 0 {
		r.PartialSuccess = true
	}
}
