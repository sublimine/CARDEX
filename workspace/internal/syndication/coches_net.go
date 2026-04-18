package syndication

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"strings"
	"time"
)

// cochesNetAdapter implements Platform for coches.net.
//
// coches.net (Adevinta Spain) does not offer a public dealer API.
// This adapter exports XML in the coches.net XML import format used by
// their dealer portal bulk upload.
type cochesNetAdapter struct{}

func init() { Register(&cochesNetAdapter{}) }

func (a *cochesNetAdapter) Name() string               { return "coches_net" }
func (a *cochesNetAdapter) SupportedCountries() []string { return []string{"ES"} }

// cochesNetVehicle is the XML structure for coches.net import.
type cochesNetVehicle struct {
	XMLName       xml.Name `xml:"anuncio"`
	Referencia    string   `xml:"referencia"`
	Marca         string   `xml:"marca"`
	Modelo        string   `xml:"modelo"`
	Version       string   `xml:"version,omitempty"`
	Anyo          int      `xml:"anyo"`
	Kilometros    int      `xml:"kilometros"`
	Combustible   string   `xml:"combustible"`
	Cambio        string   `xml:"cambio"`
	Potencia      int      `xml:"potencia,omitempty"`
	Color         string   `xml:"color,omitempty"`
	Carroceria    string   `xml:"carroceria,omitempty"`
	Precio        int64    `xml:"precio"` // cents
	Descripcion   string   `xml:"descripcion,omitempty"`
	Fotos         cochesNetFotos
	Vendedor      cochesNetVendedor
}

type cochesNetFotos struct {
	XMLName xml.Name `xml:"fotos"`
	URLs    []string `xml:"foto"`
}

type cochesNetVendedor struct {
	XMLName   xml.Name `xml:"vendedor"`
	Nombre    string   `xml:"nombre"`
	Provincia string   `xml:"provincia,omitempty"`
	Telefono  string   `xml:"telefono,omitempty"`
	Email     string   `xml:"email,omitempty"`
}

func (a *cochesNetAdapter) ValidateListing(l PlatformListing) []ValidationError {
	var errs []ValidationError
	if strings.TrimSpace(l.Make) == "" {
		errs = append(errs, ValidationError{Field: "Make", Message: "marca requerida"})
	}
	if strings.TrimSpace(l.Model) == "" {
		errs = append(errs, ValidationError{Field: "Model", Message: "modelo requerido"})
	}
	if l.Price <= 0 {
		errs = append(errs, ValidationError{Field: "Price", Message: "precio debe ser > 0"})
	}
	if l.Year < 1900 || l.Year > time.Now().Year()+2 {
		errs = append(errs, ValidationError{Field: "Year", Message: "año inválido"})
	}
	if strings.TrimSpace(l.FuelType) == "" {
		errs = append(errs, ValidationError{Field: "FuelType", Message: "combustible requerido"})
	}
	return errs
}

func (a *cochesNetAdapter) buildXML(l PlatformListing) ([]byte, error) {
	photos := TruncatePhotos(l.PhotoURLs, 20)
	v := cochesNetVehicle{
		Referencia:  l.VehicleID,
		Marca:       strings.ToUpper(l.Make),
		Modelo:      l.Model,
		Version:     l.Variant,
		Anyo:        l.Year,
		Kilometros:  l.MileageKM,
		Combustible: mapFuelToCochesNet(l.FuelType),
		Cambio:      mapTransToCochesNet(l.Transmission),
		Potencia:    l.PowerKW,
		Color:       l.Color,
		Carroceria:  l.BodyType,
		Precio:      l.Price,
		Descripcion: l.Description,
		Fotos:       cochesNetFotos{URLs: photos},
		Vendedor: cochesNetVendedor{
			Nombre:   l.DealerName,
			Telefono: l.ContactPhone,
			Email:    l.ContactEmail,
		},
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

func (a *cochesNetAdapter) Publish(_ context.Context, l PlatformListing) (string, string, error) {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return "", "", fmt.Errorf("coches.net validation: %s", errs[0].Error())
	}
	if _, err := a.buildXML(l); err != nil {
		return "", "", fmt.Errorf("coches.net XML: %w", err)
	}
	extID := "cn-" + l.VehicleID
	extURL := "https://www.coches.net/segunda-mano/-/" + extID + ".htm"
	return extID, extURL, nil
}

func (a *cochesNetAdapter) Update(_ context.Context, _ string, l PlatformListing) error {
	if errs := a.ValidateListing(l); len(errs) > 0 {
		return fmt.Errorf("coches.net validation: %s", errs[0].Error())
	}
	_, err := a.buildXML(l)
	return err
}

func (a *cochesNetAdapter) Withdraw(_ context.Context, _ string) error { return nil }

func (a *cochesNetAdapter) Status(_ context.Context, externalID string) (PlatformStatus, error) {
	return PlatformStatus{ExternalID: externalID, State: "active", UpdatedAt: time.Now()}, nil
}

func mapFuelToCochesNet(f string) string {
	switch NormaliseFuelType(f) {
	case "electric":
		return "Electrico"
	case "hybrid_plugin":
		return "Hibrido Enchufable"
	case "hybrid":
		return "Hibrido"
	case "diesel":
		return "Diesel"
	case "lpg":
		return "Gas Licuado (LPG)"
	case "cng":
		return "Gas Natural"
	default:
		return "Gasolina"
	}
}

func mapTransToCochesNet(t string) string {
	if NormaliseTransmission(t) == "automatic" {
		return "Automatico"
	}
	return "Manual"
}
