package syndication

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// leboncoinAdapter implements Platform for leboncoin.fr.
//
// leboncoin does not offer a public dealer API. Listings are exported as
// CSV in the leboncoin pro import format and submitted via their dealer portal.
type leboncoinAdapter struct{}

func init() { Register(&leboncoinAdapter{}) }

func (a *leboncoinAdapter) Name() string               { return "leboncoin" }
func (a *leboncoinAdapter) SupportedCountries() []string { return []string{"FR"} }

func (a *leboncoinAdapter) ValidateListing(l PlatformListing) []ValidationError {
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
	if l.Year < 1900 || l.Year > time.Now().Year()+2 {
		errs = append(errs, ValidationError{Field: "Year", Message: "invalid model year"})
	}
	if l.DealerCountry != "" && strings.ToUpper(l.DealerCountry) != "FR" {
		errs = append(errs, ValidationError{Field: "DealerCountry", Message: "leboncoin supports FR only"})
	}
	return errs
}

func (a *leboncoinAdapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("leboncoin validation: %s", errs[0].Error())
	}
	extID := "lbc-" + l.VehicleID
	extURL := "https://www.leboncoin.fr/voitures/" + extID + ".htm"
	return extID, extURL, nil
}

func (a *leboncoinAdapter) Update(_ context.Context, _ string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("leboncoin validation: %s", errs[0].Error())
	}
	return nil
}

func (a *leboncoinAdapter) Withdraw(_ context.Context, _ string) error { return nil }

func (a *leboncoinAdapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{ExternalID: externalID, State: "active", UpdatedAt: time.Now()}, nil
}

// LeboncoinCSVRow returns a single CSV row for this listing (leboncoin pro import format).
func LeboncoinCSVRow(l PlatformListing) []string {
	title := fmt.Sprintf("%s %s", strings.TrimSpace(l.Make), strings.TrimSpace(l.Model))
	if l.Variant != "" {
		title += " " + l.Variant
	}
	desc := l.Description
	if desc == "" {
		desc = GenerateDescription("FR", DescriptionData{
			Make: l.Make, Model: l.Model, Variant: l.Variant,
			Year: l.Year, MileageKM: l.MileageKM,
			FuelType: l.FuelType, Transmission: l.Transmission,
			PowerKW: l.PowerKW, Color: l.Color,
			Price:      FormatPrice(l.Price, l.Currency),
			DealerName: l.DealerName,
		})
	}
	photo := ""
	if len(l.PhotoURLs) > 0 {
		photo = l.PhotoURLs[0]
	}
	return []string{
		l.VehicleID,
		title,
		desc,
		fmt.Sprintf("%.0f", float64(l.Price)/100),
		"voitures",
		"FR",
		fmt.Sprintf("%d", l.Year),
		fmt.Sprintf("%d", l.MileageKM),
		l.FuelType,
		l.Transmission,
		photo,
		l.DealerName,
		l.ContactPhone,
		l.ContactEmail,
	}
}

// LeboncoinCSVHeader returns the header row for leboncoin CSV exports.
func LeboncoinCSVHeader() []string {
	return []string{
		"reference", "titre", "description", "prix",
		"categorie", "localisation", "annee", "kilometrage",
		"carburant", "boite", "photo_principale",
		"vendeur", "telephone", "email",
	}
}
