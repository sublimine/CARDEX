package syndication

import (
	"strings"
	"text/template"
	"bytes"
)

// DescriptionData holds the values substituted into description templates.
type DescriptionData struct {
	Make        string
	Model       string
	Variant     string
	Year        int
	MileageKM   int
	FuelType    string
	Transmission string
	PowerKW     int
	Color       string
	BodyType    string
	FeaturesList string // comma-separated features
	Price       string  // formatted price string
	DealerName  string
	// AIGeneratedDescription is reserved for future NLG integration.
	// When non-empty, it takes precedence over the template output.
	AIGeneratedDescription string
}

// descriptionTemplates holds per-language templates.
var descriptionTemplates = map[string]string{
	"DE": `{{.Make}} {{.Model}}{{if .Variant}} {{.Variant}}{{end}}, {{.Year}}, {{.MileageKM}} km, {{.FuelType}}, {{.Transmission}}. Leistung: {{.PowerKW}} kW. Farbe: {{.Color}}.{{if .FeaturesList}} Ausstattung: {{.FeaturesList}}.{{end}} Preis: {{.Price}}. Angeboten von {{.DealerName}}.`,
	"FR": `{{.Make}} {{.Model}}{{if .Variant}} {{.Variant}}{{end}}, {{.Year}}, {{.MileageKM}} km, {{.FuelType}}, {{.Transmission}}. Puissance: {{.PowerKW}} kW. Couleur: {{.Color}}.{{if .FeaturesList}} Équipements: {{.FeaturesList}}.{{end}} Prix: {{.Price}}. Proposé par {{.DealerName}}.`,
	"ES": `{{.Make}} {{.Model}}{{if .Variant}} {{.Variant}}{{end}}, {{.Year}}, {{.MileageKM}} km, {{.FuelType}}, {{.Transmission}}. Potencia: {{.PowerKW}} kW. Color: {{.Color}}.{{if .FeaturesList}} Equipamiento: {{.FeaturesList}}.{{end}} Precio: {{.Price}}. Ofrecido por {{.DealerName}}.`,
	"NL": `{{.Make}} {{.Model}}{{if .Variant}} {{.Variant}}{{end}}, {{.Year}}, {{.MileageKM}} km, {{.FuelType}}, {{.Transmission}}. Vermogen: {{.PowerKW}} kW. Kleur: {{.Color}}.{{if .FeaturesList}} Opties: {{.FeaturesList}}.{{end}} Prijs: {{.Price}}. Aangeboden door {{.DealerName}}.`,
	"EN": `{{.Make}} {{.Model}}{{if .Variant}} {{.Variant}}{{end}}, {{.Year}}, {{.MileageKM}} km, {{.FuelType}}, {{.Transmission}}. Power: {{.PowerKW}} kW. Colour: {{.Color}}.{{if .FeaturesList}} Features: {{.FeaturesList}}.{{end}} Price: {{.Price}}. Offered by {{.DealerName}}.`,
}

// GenerateDescription produces a localised description from d.
// If d.AIGeneratedDescription is set it takes precedence.
// Falls back to "EN" if the requested language has no template.
func GenerateDescription(lang string, d DescriptionData) string {
	if d.AIGeneratedDescription != "" {
		return d.AIGeneratedDescription
	}
	lang = strings.ToUpper(strings.TrimSpace(lang))
	tplStr, ok := descriptionTemplates[lang]
	if !ok {
		tplStr = descriptionTemplates["EN"]
	}
	tpl, err := template.New("desc").Parse(tplStr)
	if err != nil {
		return ""
	}
	var buf bytes.Buffer
	if err := tpl.Execute(&buf, d); err != nil {
		return ""
	}
	return buf.String()
}

// SupportedLanguages returns the language codes that have a template.
func SupportedLanguages() []string {
	langs := make([]string, 0, len(descriptionTemplates))
	for k := range descriptionTemplates {
		langs = append(langs, k)
	}
	return langs
}
