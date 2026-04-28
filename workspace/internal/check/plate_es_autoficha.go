package check

// autofichaResolver queries the autoficha.com AWS AppSync backend for ES plate data.
//
// Source: DGT INTV data proxied through autoficha's GraphQL API.
// API endpoint and key extracted from the Android APK (v1, Jan 2024).
//
// Used as a fallback when comprobarmatricula.com is unreachable (Cloudflare
// blocks datacenter IPs). Both sources ultimately read from DGT INTV.
//
// Rotate key if this starts returning 401: extract new key from updated APK.

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const (
	afEndpoint = "https://2sq7c2ojwjcevkft3hv6uspfqq.appsync-api.eu-west-3.amazonaws.com/graphql"
	afAPIKey   = "da2-5qw4535jhbbmzaslbspbpxcsma"
)

const afQuery = `
query GetInfoVehiculo($id: String!) {
  getInfoVehiculo(id: $id) {
    __typename
    ... on IHeader  { title subtitle description image }
    ... on IContent { title icon values { title value textColor backgroundColor } }
    ... on ITable   { title icon values { title textColor backgroundColor values { title value textColor backgroundColor } } }
    ... on IAlert   { alert_type title description links { title value } }
    ... on IBubbleGroup { bubbles { icon texts } }
    ... on IThumbnail   { principalText title subtitle image }
    ... on IChipGroup   { chips { title url } }
  }
}`

// afBlock is a single polymorphic block from the autoficha response.
type afBlock struct {
	Typename    string     `json:"__typename"`
	// IContent / ITable
	Title       string     `json:"title,omitempty"`
	Icon        string     `json:"icon,omitempty"`
	Values      []afValue  `json:"values,omitempty"`
	// IAlert
	AlertType   string     `json:"alert_type,omitempty"`
	Description []string   `json:"description,omitempty"`
	// IBubbleGroup
	Bubbles     []afBubble `json:"bubbles,omitempty"`
	// IThumbnail
	PrincipalText string   `json:"principalText,omitempty"`
	Subtitle      string   `json:"subtitle,omitempty"`
}

type afValue struct {
	Title  string     `json:"title"`
	Value  string     `json:"value,omitempty"`
	Values []afValue  `json:"values,omitempty"` // ITable nested rows
}

type afBubble struct {
	Icon  string   `json:"icon"`
	Texts []string `json:"texts"`
}

type afResponse struct {
	Data struct {
		GetInfoVehiculo []afBlock `json:"getInfoVehiculo"`
	} `json:"data"`
	Errors []struct {
		Message string `json:"message"`
	} `json:"errors"`
}

// fetchAutoficha queries the autoficha AppSync endpoint for a normalised plate.
// Returns nil, false, nil when the plate is not found.
// Returns nil, false, err on network/auth failures.
func (r *esPlateResolver) fetchAutoficha(ctx context.Context, plate string) (*PlateResult, bool, error) {
	body := map[string]interface{}{
		"query":     afQuery,
		"variables": map[string]string{"id": "P-" + plate},
	}
	b, err := json.Marshal(body)
	if err != nil {
		return nil, false, fmt.Errorf("autoficha marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, afEndpoint, bytes.NewReader(b))
	if err != nil {
		return nil, false, fmt.Errorf("autoficha request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", afAPIKey)

	resp, err := r.client.Do(req)
	if err != nil {
		return nil, false, fmt.Errorf("autoficha unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		return nil, false, fmt.Errorf("autoficha: API key expired (rotate from APK)")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, false, fmt.Errorf("autoficha: HTTP %d", resp.StatusCode)
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	if err != nil {
		return nil, false, fmt.Errorf("autoficha read: %w", err)
	}

	var af afResponse
	if err := json.Unmarshal(raw, &af); err != nil {
		return nil, false, fmt.Errorf("autoficha decode: %w", err)
	}
	if len(af.Errors) > 0 {
		return nil, false, fmt.Errorf("autoficha GQL error: %s", af.Errors[0].Message)
	}
	if len(af.Data.GetInfoVehiculo) == 0 {
		return nil, false, nil // plate not found
	}

	result := mapAutofichaToPlate(plate, af.Data.GetInfoVehiculo)
	if result.Make == "" && result.Model == "" {
		return nil, false, nil
	}
	return result, true, nil
}

// mapAutofichaToPlate converts the autoficha block list to a PlateResult.
func mapAutofichaToPlate(plate string, blocks []afBlock) *PlateResult {
	r := &PlateResult{
		Plate:     plate,
		Country:   "ES",
		FetchedAt: time.Now().UTC(),
		Source:    "autoficha.com (DGT INTV)",
	}

	kv := func(values []afValue) map[string]string {
		m := make(map[string]string, len(values))
		for _, v := range values {
			if v.Title != "" && v.Value != "" {
				m[v.Title] = v.Value
			}
		}
		return m
	}

	for _, b := range blocks {
		switch b.Typename {
		case "IThumbnail":
			if r.Make == "" {
				r.Make = strings.TrimSpace(b.Title)
			}
			if r.Model == "" {
				r.Model = strings.TrimSpace(b.Subtitle)
			}

		case "IContent":
			m := kv(b.Values)
			switch b.Icon {
			case "car-hatchback": // Información general
				if r.Make == "" {
					r.Make = m["Marca"]
				}
				if r.Model == "" {
					r.Model = m["Modelo"]
				}
				if r.FuelType == "" {
					r.FuelType = m["Combustible"]
				}
				if r.BodyType == "" {
					r.BodyType = m["Carrocería"]
				}
				if r.VIN == "" {
					r.VIN = m["VIN"]
				}
				if r.DisplacementCC == 0 {
					r.DisplacementCC = parseCC(m["Cilindrada"])
				}
				if r.PowerCV == 0 {
					r.PowerCV = parsePowerCV(m["Potencia"])
				}
				if r.PowerKW == 0 {
					r.PowerKW = parsePowerKW(m["Potencia"])
				}
				if r.NumberOfSeats == 0 {
					if n, err := strconv.Atoi(m["Número de plazas"]); err == nil {
						r.NumberOfSeats = n
					}
				}
				if r.EuroNorm == "" {
					r.EuroNorm = m["Homologación"]
				}

			case "calendar-clock": // Matriculación
				if r.FirstRegistration == nil {
					r.FirstRegistration = parseDMY(m["Primera matriculación"])
				}
				if r.District == "" {
					r.District = m["Provincia"]
				}

			case "car-info": // Información detallada
				if r.EmptyWeightKg == 0 {
					r.EmptyWeightKg = parseIntKg(m["Masa en circulación"])
				}
				if r.GrossWeightKg == 0 {
					r.GrossWeightKg = parseIntKg(m["Masa Máxima en carga"])
				}
				if r.WheelbaseCm == 0 {
					r.WheelbaseCm = parseMMtoCM(m["Distancia entre ejes"])
				}
				if r.Variant == "" {
					r.Variant = m["Variante"]
				}

			case "fuel": // Combustibles y emisiones
				if r.CO2GPerKm == 0 {
					r.CO2GPerKm = parseCO2(m["Emisiones CO2"])
				}
				if r.FuelType == "" {
					r.FuelType = m["Combustible"]
				}

			case "account-outline": // Propietario actual
				r.LastTransactionDate = parseDMY(m["Fecha trámite"])
				if r.ServiceCode == "" {
					r.ServiceCode = m["Servicio"]
				}
			}

		case "ITable":
			switch b.Icon {
			case "account-switch": // Propietarios (N) — full ownership timeline
				owners := parseOwnerTable(b.Values)
				r.OwnerHistory = owners
				r.TransferCount = len(owners)
				if r.TransferCount > 0 {
					r.PreviousOwners = r.TransferCount - 1
				}

			case "book-edit-outline": // Movimientos (N) — matriculaciones + transferencias
				r.MovementHistory = parseMovementTable(b.Values)
			}

		case "IAlert":
			switch b.AlertType {
			case "HIGH", "CRITICAL":
				desc := strings.Join(b.Description, " ")
				lower := strings.ToLower(desc)
				switch {
				case strings.Contains(lower, "embargo"):
					r.EmbargoFlag = true
				case strings.Contains(lower, "robado") || strings.Contains(lower, "sustracción"):
					r.StolenFlag = true
				case strings.Contains(lower, "precinto"):
					r.PrecintedFlag = true
				}
			}
		}
	}

	return r
}

// ── field parsers ─────────────────────────────────────────────────────────────

// parseCC extracts integer cc from "1968 cc".
func parseCC(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	parts := strings.Fields(s)
	if len(parts) == 0 {
		return 0
	}
	n, _ := strconv.Atoi(parts[0])
	return n
}

// parsePowerCV extracts CV from "170 CV (125.00 kW)".
func parsePowerCV(s string) int {
	idx := strings.Index(s, " CV")
	if idx < 0 {
		return 0
	}
	n, _ := strconv.Atoi(strings.TrimSpace(s[:idx]))
	return n
}

// parsePowerKW extracts kW from "170 CV (125.00 kW)".
func parsePowerKW(s string) float64 {
	start := strings.Index(s, "(")
	end := strings.Index(s, " kW")
	if start < 0 || end < 0 || end <= start {
		return 0
	}
	f, _ := strconv.ParseFloat(strings.TrimSpace(s[start+1:end]), 64)
	return f
}

// parseDMY parses "DD/MM/YYYY" → *time.Time.
func parseDMY(s string) *time.Time {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	t, err := time.Parse("02/01/2006", s)
	if err != nil {
		return nil
	}
	return &t
}

// parseIntKg extracts an integer from "1681 kg".
func parseIntKg(s string) int {
	parts := strings.Fields(s)
	if len(parts) == 0 {
		return 0
	}
	n, _ := strconv.Atoi(parts[0])
	return n
}

// parseMMtoCM converts "2605 mm" → cm integer.
func parseMMtoCM(s string) int {
	parts := strings.Fields(s)
	if len(parts) == 0 {
		return 0
	}
	mm, _ := strconv.Atoi(parts[0])
	return mm / 10
}

// parseCO2 extracts g/km integer from "172 g/km".
func parseCO2(s string) float64 {
	parts := strings.Fields(s)
	if len(parts) == 0 {
		return 0
	}
	f, _ := strconv.ParseFloat(parts[0], 64)
	return f
}

// countTableRows counts top-level rows in an ITable values list.
func countTableRows(values []afValue) int {
	count := 0
	for _, v := range values {
		if v.Title != "" {
			count++
		}
	}
	return count
}

// parseOwnerTable extracts the full owner history from the "Propietarios (N)" ITable.
// Each top-level row has title=date and nested values with Municipio/Provincia/etc.
func parseOwnerTable(rows []afValue) []OwnerEntry {
	owners := make([]OwnerEntry, 0, len(rows))
	for _, row := range rows {
		entry := OwnerEntry{
			Date: parseDMY(row.Title),
		}
		for _, v := range row.Values {
			switch v.Title {
			case "Municipio":
				entry.Municipio = v.Value
			case "Provincia":
				entry.Provincia = v.Value
			case "Tiempo en propiedad":
				entry.TimeInPossession = v.Value
			case "Tipo de persona":
				entry.PersonType = v.Value
			case "Servicio":
				entry.ServiceCode = v.Value
			}
		}
		owners = append(owners, entry)
	}
	return owners
}

// parseMovementTable extracts the full movement history from "Movimientos (N)" ITable.
// Each top-level row has title=movement type and nested values with Fecha/Municipio/etc.
func parseMovementTable(rows []afValue) []MovementEntry {
	movements := make([]MovementEntry, 0, len(rows))
	for _, row := range rows {
		entry := MovementEntry{Type: row.Title}
		for _, v := range row.Values {
			switch v.Title {
			case "Fecha":
				entry.Date = parseDMY(v.Value)
			case "Municipio":
				entry.Municipio = v.Value
			case "Provincia":
				entry.Provincia = v.Value
			case "Duración":
				entry.Duration = v.Value
			}
		}
		movements = append(movements, entry)
	}
	return movements
}
