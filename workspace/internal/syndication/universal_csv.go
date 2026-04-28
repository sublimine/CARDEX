package syndication

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"strings"
	"time"
)

// universalCSVAdapter implements Platform as a fallback CSV exporter.
// Any platform that lacks a native adapter can use this to produce a
// standard CSV file importable by most automotive portals.
type universalCSVAdapter struct{}

func init() { Register(&universalCSVAdapter{}) }

func (a *universalCSVAdapter) Name() string               { return "universal_csv" }
func (a *universalCSVAdapter) SupportedCountries() []string { return []string{"*"} }

func (a *universalCSVAdapter) ValidateListing(l PlatformListing) []ValidationError {
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

// CSVHeader returns the standard column names.
func CSVHeader() []string {
	return []string{
		"vehicle_id", "vin", "make", "model", "variant",
		"year", "mileage_km", "fuel_type", "transmission",
		"power_kw", "color", "body_type",
		"price_cents", "currency",
		"description", "features",
		"photo_url_1", "photo_url_2", "photo_url_3",
		"dealer_name", "dealer_country", "dealer_vat_id",
		"contact_email", "contact_phone",
	}
}

// CSVRow converts a PlatformListing into a CSV row aligned with CSVHeader.
func CSVRow(l PlatformListing) []string {
	photos := TruncatePhotos(l.PhotoURLs, 3)
	for len(photos) < 3 {
		photos = append(photos, "")
	}
	return []string{
		l.VehicleID,
		l.VIN,
		l.Make,
		l.Model,
		l.Variant,
		fmt.Sprintf("%d", l.Year),
		fmt.Sprintf("%d", l.MileageKM),
		NormaliseFuelType(l.FuelType),
		NormaliseTransmission(l.Transmission),
		fmt.Sprintf("%d", l.PowerKW),
		l.Color,
		l.BodyType,
		fmt.Sprintf("%d", l.Price),
		l.Currency,
		l.Description,
		strings.Join(l.Features, "|"),
		photos[0], photos[1], photos[2],
		l.DealerName,
		l.DealerCountry,
		SanitiseVATID(l.DealerVATID),
		l.ContactEmail,
		l.ContactPhone,
	}
}

// GenerateCSV encodes a slice of listings as CSV bytes (including header row).
func GenerateCSV(listings []PlatformListing) ([]byte, error) {
	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	if err := w.Write(CSVHeader()); err != nil {
		return nil, err
	}
	for _, l := range listings {
		if err := w.Write(CSVRow(l)); err != nil {
			return nil, err
		}
	}
	w.Flush()
	return buf.Bytes(), w.Error()
}

func (a *universalCSVAdapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("universal_csv validation: %s", errs[0].Error())
	}
	extID := "csv-" + l.VehicleID
	return extID, "", nil
}

func (a *universalCSVAdapter) Update(_ context.Context, _ string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("universal_csv validation: %s", errs[0].Error())
	}
	return nil
}

func (a *universalCSVAdapter) Withdraw(_ context.Context, _ string) error { return nil }

func (a *universalCSVAdapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{ExternalID: externalID, State: "active", UpdatedAt: time.Now()}, nil
}
