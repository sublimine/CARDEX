package syndication

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"strings"
	"time"
)

// autoScout24Adapter implements Platform for AutoScout24.
//
// AutoScout24 exposes a Classified Dealer API (REST + XML import) to partners.
// Public documentation is available at developers.autoscout24.com for partners.
// This adapter produces XML in the AutoScout24 import format and provides a
// REST API surface for future live integration.
//
// Country variants (.de, .be, .ch, .fr, .nl, .es) share the same adapter
// with per-country configuration supplied via NewAutoScout24.
type autoScout24Adapter struct {
	country  string // "DE", "BE", "CH", "FR", "NL", "ES"
	platform string // "autoscout24", "autoscout24_be", etc.
}

func init() {
	Register(NewAutoScout24("DE"))
	Register(NewAutoScout24("BE"))
	Register(NewAutoScout24("CH"))
}

// NewAutoScout24 constructs a country-specific AutoScout24 adapter.
func NewAutoScout24(country string) Platform {
	country = strings.ToUpper(country)
	name := "autoscout24"
	if country != "DE" {
		name = "autoscout24_" + strings.ToLower(country)
	}
	return &autoScout24Adapter{country: country, platform: name}
}

func (a *autoScout24Adapter) Name() string { return a.platform }
func (a *autoScout24Adapter) SupportedCountries() []string {
	return []string{a.country}
}

// as24Vehicle is the XML structure for AutoScout24 feed import.
type as24Vehicle struct {
	XMLName      xml.Name   `xml:"classifieds"`
	Ad           as24Ad     `xml:"ad"`
}

type as24Ad struct {
	Action       string     `xml:"action,attr"` // "insert", "update", "delete"
	ExternalID   string     `xml:"externalId"`
	Vehicle      as24Veh    `xml:"vehicle"`
	Price        as24Price  `xml:"price"`
	Description  string     `xml:"description,omitempty"`
	Photos       []as24Photo `xml:"images>image"`
	Contact      as24Contact `xml:"contact"`
}

type as24Veh struct {
	Make         string `xml:"make"`
	Model        string `xml:"model"`
	Version      string `xml:"version,omitempty"`
	Year         int    `xml:"year"`
	Mileage      int    `xml:"mileage"`
	FuelType     string `xml:"fuelType"`
	Transmission string `xml:"transmission"`
	PowerKW      int    `xml:"powerKw,omitempty"`
	BodyType     string `xml:"bodyType,omitempty"`
	Color        string `xml:"colour,omitempty"`
}

type as24Price struct {
	Amount   int64  `xml:"amount"`
	Currency string `xml:"currency"`
}

type as24Photo struct {
	URL string `xml:",chardata"`
}

type as24Contact struct {
	Name    string `xml:"name"`
	Country string `xml:"country"`
	VATID   string `xml:"vatId,omitempty"`
	Email   string `xml:"email,omitempty"`
	Phone   string `xml:"phone,omitempty"`
}

func (a *autoScout24Adapter) ValidateListing(l PlatformListing) []ValidationError {
	var errs []ValidationError
	if strings.TrimSpace(l.Make) == "" {
		errs = append(errs, ValidationError{Field: "Make", Message: "required by AutoScout24"})
	}
	if strings.TrimSpace(l.Model) == "" {
		errs = append(errs, ValidationError{Field: "Model", Message: "required by AutoScout24"})
	}
	if l.Price <= 0 {
		errs = append(errs, ValidationError{Field: "Price", Message: "must be > 0"})
	}
	if l.Year < 1900 || l.Year > time.Now().Year()+2 {
		errs = append(errs, ValidationError{Field: "Year", Message: "invalid model year"})
	}
	if strings.TrimSpace(l.FuelType) == "" {
		errs = append(errs, ValidationError{Field: "FuelType", Message: "required by AutoScout24"})
	}
	if len(l.PhotoURLs) > 50 {
		errs = append(errs, ValidationError{Field: "PhotoURLs", Message: "AutoScout24 max 50 photos"})
	}
	return errs
}

func (a *autoScout24Adapter) buildXML(action string, l PlatformListing) ([]byte, error) {
	photos := TruncatePhotos(l.PhotoURLs, 50)
	as24Photos := make([]as24Photo, len(photos))
	for i, u := range photos {
		as24Photos[i] = as24Photo{URL: u}
	}
	doc := as24Vehicle{
		Ad: as24Ad{
			Action:     action,
			ExternalID: l.VehicleID,
			Vehicle: as24Veh{
				Make:         l.Make,
				Model:        l.Model,
				Version:      l.Variant,
				Year:         l.Year,
				Mileage:      l.MileageKM,
				FuelType:     mapFuelToAS24(l.FuelType),
				Transmission: mapTransToAS24(l.Transmission),
				PowerKW:      l.PowerKW,
				BodyType:     l.BodyType,
				Color:        l.Color,
			},
			Price: as24Price{
				Amount:   l.Price,
				Currency: l.Currency,
			},
			Description: l.Description,
			Photos:      as24Photos,
			Contact: as24Contact{
				Name:    l.DealerName,
				Country: l.DealerCountry,
				VATID:   SanitiseVATID(l.DealerVATID),
				Email:   l.ContactEmail,
				Phone:   l.ContactPhone,
			},
		},
	}
	var buf bytes.Buffer
	buf.WriteString(xml.Header)
	enc := xml.NewEncoder(&buf)
	enc.Indent("", "  ")
	if err := enc.Encode(doc); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func (a *autoScout24Adapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("autoscout24 validation: %s", errs[0].Error())
	}
	if _, err := a.buildXML("insert", l); err != nil {
		return "", "", fmt.Errorf("autoscout24 XML: %w", err)
	}
	extID := "as24-" + strings.ToLower(a.country) + "-" + l.VehicleID
	extURL := fmt.Sprintf("https://www.autoscout24.%s/annonces/%s",
		strings.ToLower(a.country), extID)
	return extID, extURL, nil
}

func (a *autoScout24Adapter) Update(_ context.Context, _ string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("autoscout24 validation: %s", errs[0].Error())
	}
	_, err := a.buildXML("update", l)
	return err
}

func (a *autoScout24Adapter) Withdraw(_ context.Context, _ string) error { return nil }

func (a *autoScout24Adapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{ExternalID: externalID, State: "active", UpdatedAt: time.Now()}, nil
}

func mapFuelToAS24(f string) string {
	switch NormaliseFuelType(f) {
	case "electric":
		return "E"
	case "hybrid_plugin":
		return "2"
	case "hybrid":
		return "3"
	case "diesel":
		return "D"
	case "lpg":
		return "L"
	case "cng":
		return "C"
	default:
		return "B"
	}
}

func mapTransToAS24(t string) string {
	if NormaliseTransmission(t) == "automatic" {
		return "A"
	}
	return "M"
}
