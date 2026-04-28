package check

// plate_de_api.go — German plate lookup via CarsXE
//
// CarsXE provides plate→vehicle data for 20+ countries via REST.
// Registration: https://carsxe.com/ (7-day free trial, then pay per query)
// Pricing: ~$0.01–0.05/query depending on plan.
//
// Configure via env var: DE_PLATE_API_KEY=<your-carsxe-api-key>
//
// Response fields: make, model, year, fuel, engine (cc, power, cylinders),
//                  transmission, body style, color, VIN (when available)

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// deAPIResolver wraps the CarsXE plate decoder for Germany.
type deAPIResolver struct {
	client *http.Client
	apiKey string
	base   *dePlateResolver // fallback for district extraction
}

// newDEAPIResolver creates a DE resolver that uses CarsXE for full data
// and falls back to district-only extraction on API error.
func newDEAPIResolver(client *http.Client, apiKey string) *deAPIResolver {
	return &deAPIResolver{
		client: client,
		apiKey: apiKey,
		base:   &dePlateResolver{},
	}
}

type carsxeResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	Make    struct {
		Name string `json:"name"`
	} `json:"make"`
	Model struct {
		Name string `json:"name"`
	} `json:"model"`
	Year  string `json:"year"`
	Fuel  struct {
		Name string `json:"name"`
	} `json:"fuel"`
	Engine struct {
		PowerPS   string `json:"power_ps"`
		CC        string `json:"cc"`
		Cylinders string `json:"cylinders"`
	} `json:"engine"`
	Transmission struct {
		Name string `json:"name"`
	} `json:"transmission"`
	Body struct {
		Name string `json:"name"`
	} `json:"body"`
	Color struct {
		Name string `json:"name"`
	} `json:"color"`
	VIN string `json:"vin"`
}

func (r *deAPIResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateDEPlate(plate); err != nil {
		return nil, err
	}

	apiURL := fmt.Sprintf(
		"https://api.carsxe.com/v2/platedecoder?key=%s&plate=%s&country=DE",
		r.apiKey, plate,
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("DE CarsXE request: %w", err)
	}
	req.Header.Set("User-Agent", plateUA)

	resp, err := r.client.Do(req)
	if err != nil {
		// Network error → fall through to district-only
		return r.base.Resolve(ctx, plate)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))

	var data carsxeResponse
	if err := json.Unmarshal(body, &data); err != nil || !data.Success {
		// API error or invalid key → fall through to district-only
		return r.base.Resolve(ctx, plate)
	}

	if data.Make.Name == "" {
		return nil, fmt.Errorf("%w: DE plate %s not found", ErrPlateNotFound, plate)
	}

	// Start with district extraction for the Zulassungsbezirk context.
	uz, district := deExtractUZ(plate)
	_ = uz

	result := &PlateResult{
		Plate:     plate,
		Country:   "DE",
		District:  district,
		Make:      strings.TrimSpace(data.Make.Name),
		Model:     strings.TrimSpace(data.Model.Name),
		FuelType:  strings.TrimSpace(data.Fuel.Name),
		BodyType:  strings.TrimSpace(data.Body.Name),
		Color:     strings.TrimSpace(data.Color.Name),
		VIN:       strings.TrimSpace(data.VIN),
		Source:    "carsxe.com (DE vehicle registry)",
		FetchedAt: time.Now().UTC(),
	}

	if yr, err := strconv.Atoi(data.Year); err == nil && yr > 1900 {
		t := time.Date(yr, 1, 1, 0, 0, 0, 0, time.UTC)
		result.FirstRegistration = &t
	}

	if cc, err := strconv.Atoi(data.Engine.CC); err == nil && cc > 0 {
		result.DisplacementCC = cc
	}
	if ps, err := strconv.ParseFloat(data.Engine.PowerPS, 64); err == nil && ps > 0 {
		result.PowerCV = int(ps)
		result.PowerKW = ps * 0.7355 // PS → kW
	}
	if cyl, err := strconv.Atoi(data.Engine.Cylinders); err == nil && cyl > 0 {
		result.NumberOfCylinders = cyl
	}

	result.Transmission = strings.TrimSpace(data.Transmission.Name)
	result.Partial = result.Make == ""
	return result, nil
}
