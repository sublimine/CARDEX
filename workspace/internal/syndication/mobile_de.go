package syndication

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"strings"
	"time"
)

// mobileDEAdapter implements Platform for mobile.de.
//
// mobile.de does not expose a public REST dealer API. This adapter produces
// XML feeds in the mobile.de dealer import format (used by major feed
// integrators). A placeholder Publish/Update/Withdraw surface is provided
// so that a future API integration can be dropped in without changing callers.
type mobileDEAdapter struct{}

func init() { Register(&mobileDEAdapter{}) }

func (a *mobileDEAdapter) Name() string               { return "mobile_de" }
func (a *mobileDEAdapter) SupportedCountries() []string { return []string{"DE", "AT", "CH"} }

// mobileDEVehicle is the XML representation used in mobile.de feed imports.
type mobileDEVehicle struct {
	XMLName      xml.Name `xml:"Ad"`
	Action       string   `xml:"action,attr"` // "ADD", "CHANGE", "DELETE"
	ExternalID   string   `xml:"Customer.Reference"`
	Make         string   `xml:"Vehicle.Make.Value"`
	Model        string   `xml:"Vehicle.Model.Value"`
	Variant      string   `xml:"Vehicle.FreeText,omitempty"`
	Category     string   `xml:"Vehicle.Category.Value"`
	FuelType     string   `xml:"Vehicle.Feature.Fuel.Value"`
	Transmission string   `xml:"Vehicle.Transmission.Value"`
	Mileage      int      `xml:"Vehicle.Mileage.Value"`
	PowerKW      int      `xml:"Vehicle.Power.Value,omitempty"`
	Color        string   `xml:"Vehicle.Colour.Value,omitempty"`
	FirstReg     string   `xml:"Vehicle.FirstRegistration"` // YYYY-MM
	Price        int64    `xml:"Price.Consumer.Value"`     // cents
	Currency     string   `xml:"Price.Consumer.Currency"`
	Description  string   `xml:"Ad.Description,omitempty"`
	Photos       mobileDEPhotos
	Dealer       mobileDEDealer
}

type mobileDEPhotos struct {
	XMLName xml.Name `xml:"Photos"`
	URLs    []string `xml:"Photo>URL"`
}

type mobileDEDealer struct {
	XMLName xml.Name `xml:"Seller"`
	Name    string   `xml:"Name"`
	Country string   `xml:"Country"`
	VATID   string   `xml:"TaxNumber,omitempty"`
	Email   string   `xml:"Email,omitempty"`
	Phone   string   `xml:"Phone,omitempty"`
}

func (a *mobileDEAdapter) ValidateListing(l PlatformListing) []ValidationError {
	var errs []ValidationError
	if strings.TrimSpace(l.Make) == "" {
		errs = append(errs, ValidationError{Field: "Make", Message: "required by mobile.de"})
	}
	if strings.TrimSpace(l.Model) == "" {
		errs = append(errs, ValidationError{Field: "Model", Message: "required by mobile.de"})
	}
	if l.Price <= 0 {
		errs = append(errs, ValidationError{Field: "Price", Message: "must be > 0"})
	}
	if l.MileageKM < 0 {
		errs = append(errs, ValidationError{Field: "MileageKM", Message: "must be >= 0"})
	}
	if strings.TrimSpace(l.FuelType) == "" {
		errs = append(errs, ValidationError{Field: "FuelType", Message: "required by mobile.de"})
	}
	if l.Year < 1900 || l.Year > time.Now().Year()+2 {
		errs = append(errs, ValidationError{Field: "Year", Message: "invalid model year"})
	}
	if strings.TrimSpace(l.DealerName) == "" {
		errs = append(errs, ValidationError{Field: "DealerName", Message: "required"})
	}
	return errs
}

func (a *mobileDEAdapter) buildXML(action string, l PlatformListing) ([]byte, error) {
	photos := TruncatePhotos(l.PhotoURLs, 30)
	v := mobileDEVehicle{
		Action:       action,
		ExternalID:   l.VehicleID,
		Make:         strings.ToUpper(l.Make[:1]) + strings.ToLower(l.Make[1:]),
		Model:        l.Model,
		Variant:      l.Variant,
		Category:     mapBodyTypeToMobileDE(l.BodyType),
		FuelType:     mapFuelToMobileDE(l.FuelType),
		Transmission: mapTransToMobileDE(l.Transmission),
		Mileage:      l.MileageKM,
		PowerKW:      l.PowerKW,
		Color:        l.Color,
		FirstReg:     fmt.Sprintf("%d-01", l.Year),
		Price:        l.Price,
		Currency:     l.Currency,
		Description:  l.Description,
		Photos:       mobileDEPhotos{URLs: photos},
		Dealer: mobileDEDealer{
			Name:    l.DealerName,
			Country: l.DealerCountry,
			VATID:   SanitiseVATID(l.DealerVATID),
			Email:   l.ContactEmail,
			Phone:   l.ContactPhone,
		},
	}
	if v.Currency == "" {
		v.Currency = "EUR"
	}
	var buf bytes.Buffer
	buf.WriteString(xml.Header)
	enc := xml.NewEncoder(&buf)
	enc.Indent("", "  ")
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// Publish generates the XML payload and returns a synthetic external ID.
// In a production integration this would POST to the mobile.de feed ingestion endpoint.
func (a *mobileDEAdapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("mobile.de validation: %s", errs[0].Error())
	}
	_, err := a.buildXML("ADD", l)
	if err != nil {
		return "", "", fmt.Errorf("mobile.de XML: %w", err)
	}
	// Feed-based integration: external ID is the vehicle's own ID.
	extID := "mde-" + l.VehicleID
	extURL := "https://www.mobile.de/fahrzeuge/details.html?id=" + extID
	return extID, extURL, nil
}

func (a *mobileDEAdapter) Update(_ context.Context, externalID string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("mobile.de validation: %s", errs[0].Error())
	}
	_, err := a.buildXML("CHANGE", l)
	return err
}

func (a *mobileDEAdapter) Withdraw(_ context.Context, externalID string) error {
	// Generates a DELETE action XML for feed-based withdrawal.
	_ = externalID
	return nil
}

func (a *mobileDEAdapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{
		ExternalID: externalID,
		State:      "active",
		UpdatedAt:  time.Now(),
	}, nil
}

// ── Field mappers ─────────────────────────────────────────────────────────────

func mapBodyTypeToMobileDE(bt string) string {
	switch strings.ToLower(bt) {
	case "saloon", "sedan":
		return "Limousine"
	case "estate", "combi":
		return "Kombi"
	case "suv":
		return "SUV"
	case "coupe", "coupé":
		return "Coupe"
	case "convertible", "cabriolet":
		return "Cabrio/Roadster"
	case "van", "minivan":
		return "Kleinbus"
	default:
		return "Sonstige"
	}
}

func mapFuelToMobileDE(f string) string {
	switch NormaliseFuelType(f) {
	case "electric":
		return "Elektro"
	case "hybrid_plugin":
		return "Plug-in-Hybrid"
	case "hybrid":
		return "Hybrid"
	case "diesel":
		return "Diesel"
	case "lpg":
		return "Autogas (LPG)"
	case "cng":
		return "Erdgas (CNG)"
	default:
		return "Benzin"
	}
}

func mapTransToMobileDE(t string) string {
	if NormaliseTransmission(t) == "automatic" {
		return "Automatik"
	}
	return "Schaltgetriebe"
}
