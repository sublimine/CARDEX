package e13_vlm_vision

import (
	"encoding/json"
	"strings"

	"cardex.eu/extraction/internal/pipeline"
)

// vlmVehicleJSON is the expected JSON schema returned by the VLM.
// All fields are pointers so we can distinguish "model said zero" from "not present".
type vlmVehicleJSON struct {
	Make            *string  `json:"make"`
	Model           *string  `json:"model"`
	Year            *int     `json:"year"`
	Price           *float64 `json:"price"`
	PriceCurrency   *string  `json:"price_currency"`
	MileageKm       *int     `json:"mileage_km"`
	FuelType        *string  `json:"fuel_type"`
	Transmission    *string  `json:"transmission"`
	Color           *string  `json:"color"`
	VIN             *string  `json:"vin"`
	DealerName      *string  `json:"dealer_name"`
	DealerLocation  *string  `json:"dealer_location"`
}

// parseVLMResponse extracts vehicle data from the VLM's raw text response.
//
// The VLM is instructed to return bare JSON, but small models sometimes wrap
// the JSON in markdown code fences or add a prefix sentence. parseVLMResponse
// strips common wrappers before unmarshalling.
//
// Returns (nil, 0) when no valid JSON could be extracted.
func parseVLMResponse(raw string) (*pipeline.VehicleRaw, int) {
	cleaned := stripMarkdownFence(raw)
	if cleaned == "" {
		return nil, 0
	}

	var j vlmVehicleJSON
	if err := json.Unmarshal([]byte(cleaned), &j); err != nil {
		return nil, 0
	}

	v := &pipeline.VehicleRaw{
		AdditionalFields: make(map[string]interface{}),
	}
	fieldsExtracted := 0

	if j.Make != nil && *j.Make != "" {
		v.Make = j.Make
		fieldsExtracted++
	}
	if j.Model != nil && *j.Model != "" {
		v.Model = j.Model
		fieldsExtracted++
	}
	if j.Year != nil && *j.Year > 1886 && *j.Year < 2100 {
		v.Year = j.Year
		fieldsExtracted++
	}
	if j.Price != nil && *j.Price > 0 {
		v.PriceGross = j.Price
		if j.PriceCurrency != nil && *j.PriceCurrency != "" {
			v.Currency = j.PriceCurrency
		}
		fieldsExtracted++
	}
	if j.MileageKm != nil && *j.MileageKm >= 0 {
		v.Mileage = j.MileageKm
		fieldsExtracted++
	}
	if j.FuelType != nil && *j.FuelType != "" {
		v.FuelType = j.FuelType
		fieldsExtracted++
	}
	if j.Transmission != nil && *j.Transmission != "" {
		v.Transmission = j.Transmission
		fieldsExtracted++
	}
	if j.Color != nil && *j.Color != "" {
		v.Color = j.Color
		fieldsExtracted++
	}
	if j.VIN != nil && len(*j.VIN) >= 17 {
		v.VIN = j.VIN
		fieldsExtracted++
	}
	if j.DealerName != nil && *j.DealerName != "" {
		v.AdditionalFields["dealer_name"] = *j.DealerName
		fieldsExtracted++
	}
	if j.DealerLocation != nil && *j.DealerLocation != "" {
		v.AdditionalFields["dealer_location"] = *j.DealerLocation
		fieldsExtracted++
	}

	if fieldsExtracted == 0 {
		return nil, 0
	}
	return v, fieldsExtracted
}

// stripMarkdownFence removes common VLM output wrappers:
// - ```json ... ``` code fences
// - ``` ... ``` code fences (no language tag)
// - leading/trailing whitespace
// - any text before the first '{' or after the last '}'
func stripMarkdownFence(s string) string {
	s = strings.TrimSpace(s)

	// Strip ```json ... ``` or ``` ... ```
	if strings.HasPrefix(s, "```") {
		end := strings.LastIndex(s, "```")
		if end > 3 {
			s = s[3:end]
			// strip optional language tag on first line
			if nl := strings.IndexByte(s, '\n'); nl != -1 {
				s = s[nl+1:]
			}
			s = strings.TrimSpace(s)
		}
	}

	// Extract the JSON object between first '{' and last '}'
	start := strings.IndexByte(s, '{')
	end := strings.LastIndexByte(s, '}')
	if start < 0 || end <= start {
		return ""
	}
	return s[start : end+1]
}
