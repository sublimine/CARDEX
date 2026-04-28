package syndication

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"strings"
	"time"
)

// universalXMLAdapter implements Platform as a fallback XML exporter.
type universalXMLAdapter struct{}

func init() { Register(&universalXMLAdapter{}) }

func (a *universalXMLAdapter) Name() string               { return "universal_xml" }
func (a *universalXMLAdapter) SupportedCountries() []string { return []string{"*"} }

// universalListing is the schema-agnostic XML representation.
type universalListing struct {
	XMLName      xml.Name         `xml:"listing"`
	VehicleID    string           `xml:"vehicleId"`
	VIN          string           `xml:"vin,omitempty"`
	Make         string           `xml:"make"`
	Model        string           `xml:"model"`
	Variant      string           `xml:"variant,omitempty"`
	Year         int              `xml:"year"`
	MileageKM    int              `xml:"mileageKm"`
	FuelType     string           `xml:"fuelType"`
	Transmission string           `xml:"transmission"`
	PowerKW      int              `xml:"powerKw,omitempty"`
	Color        string           `xml:"color,omitempty"`
	BodyType     string           `xml:"bodyType,omitempty"`
	PriceCents   int64            `xml:"priceCents"`
	Currency     string           `xml:"currency"`
	Description  string           `xml:"description,omitempty"`
	Features     universalFeatures
	Photos       universalPhotos
	Dealer       universalDealer
}

type universalFeatures struct {
	XMLName xml.Name `xml:"features"`
	Items   []string `xml:"feature"`
}

type universalPhotos struct {
	XMLName xml.Name `xml:"photos"`
	URLs    []string `xml:"photo"`
}

type universalDealer struct {
	XMLName xml.Name `xml:"dealer"`
	Name    string   `xml:"name"`
	Country string   `xml:"country,omitempty"`
	VATID   string   `xml:"vatId,omitempty"`
	Email   string   `xml:"email,omitempty"`
	Phone   string   `xml:"phone,omitempty"`
}

// universalListings wraps multiple listings for batch export.
type universalListings struct {
	XMLName  xml.Name           `xml:"listings"`
	Listings []universalListing `xml:"listing"`
}

// GenerateXML encodes a slice of PlatformListings as XML bytes.
func GenerateXML(listings []PlatformListing) ([]byte, error) {
	var items []universalListing
	for _, l := range listings {
		items = append(items, toUniversalListing(l))
	}
	doc := universalListings{Listings: items}
	var buf bytes.Buffer
	buf.WriteString(xml.Header)
	enc := xml.NewEncoder(&buf)
	enc.Indent("", "  ")
	if err := enc.Encode(doc); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func toUniversalListing(l PlatformListing) universalListing {
	cur := l.Currency
	if cur == "" {
		cur = "EUR"
	}
	return universalListing{
		VehicleID:    l.VehicleID,
		VIN:          l.VIN,
		Make:         l.Make,
		Model:        l.Model,
		Variant:      l.Variant,
		Year:         l.Year,
		MileageKM:    l.MileageKM,
		FuelType:     NormaliseFuelType(l.FuelType),
		Transmission: NormaliseTransmission(l.Transmission),
		PowerKW:      l.PowerKW,
		Color:        l.Color,
		BodyType:     l.BodyType,
		PriceCents:   l.Price,
		Currency:     cur,
		Description:  l.Description,
		Features:     universalFeatures{Items: l.Features},
		Photos:       universalPhotos{URLs: l.PhotoURLs},
		Dealer: universalDealer{
			Name:    l.DealerName,
			Country: l.DealerCountry,
			VATID:   SanitiseVATID(l.DealerVATID),
			Email:   l.ContactEmail,
			Phone:   l.ContactPhone,
		},
	}
}

func (a *universalXMLAdapter) ValidateListing(l PlatformListing) []ValidationError {
	var errs []ValidationError
	if strings.TrimSpace(l.Make) == "" {
		errs = append(errs, ValidationError{Field: "Make", Message: "required"})
	}
	if strings.TrimSpace(l.Model) == "" {
		errs = append(errs, ValidationError{Field: "Model", Message: "required"})
	}
	if l.Price <= 0 {
		errs = append(errs, ValidationError{Field: "Price", Message: "must be > 0"})
	}
	return errs
}

func (a *universalXMLAdapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("universal_xml validation: %s", errs[0].Error())
	}
	extID := "xml-" + l.VehicleID
	return extID, "", nil
}

func (a *universalXMLAdapter) Update(_ context.Context, _ string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("universal_xml validation: %s", errs[0].Error())
	}
	return nil
}

func (a *universalXMLAdapter) Withdraw(_ context.Context, _ string) error { return nil }

func (a *universalXMLAdapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{ExternalID: externalID, State: "active", UpdatedAt: time.Now()}, nil
}
