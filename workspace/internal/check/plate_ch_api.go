package check

// plate_ch_api.go — Swiss plate lookup via kennzeichenapi.ch
//
// kennzeichenapi.ch proxies ASTRA/FEDRO cantonal data.
// Registration: https://www.kennzeichenapi.ch/ (free account, 10 lookups/month)
// Beyond free tier: 0.20 CHF/query.
//
// Configure via env var: CH_PLATE_API_KEY=<your-username>
//
// Response fields available:
//   Description, CarMake.CurrentTextValue, RegistrationYear,
//   Transmission, FuelType, EuroTypeCode (type approval), EngineSize, PowerBhp

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// chAPIResolver wraps the kennzeichenapi.ch webservice.
type chAPIResolver struct {
	client   *http.Client
	username string // kennzeichenapi.ch account username
}

// newCHAPIResolver creates a CH resolver backed by kennzeichenapi.ch.
func newCHAPIResolver(client *http.Client, username string) *chAPIResolver {
	return &chAPIResolver{client: client, username: username}
}

// chAPIResponse mirrors the XML returned by kennzeichenapi.ch.
type chAPIResponse struct {
	XMLName         xml.Name `xml:"VehicleDataResult"`
	Description     string   `xml:"Description"`
	CarMake         struct {
		CurrentTextValue string `xml:"CurrentTextValue"`
	} `xml:"CarMake"`
	CarModel        struct {
		CurrentTextValue string `xml:"CurrentTextValue"`
	} `xml:"CarModel"`
	RegistrationYear int    `xml:"RegistrationYear"`
	Transmission     string `xml:"Transmission"`
	FuelType         string `xml:"FuelType"`
	EuroTypeCode     string `xml:"EuroTypeCode"`
	EngineSize       int    `xml:"EngineSize"`
	PowerBhp         int    `xml:"PowerBhp"`
	BodyStyle        string `xml:"BodyStyle"`
	NumberOfDoors    int    `xml:"NumberOfDoors"`
	NumberOfSeats    int    `xml:"NumberOfSeats"`
	MakeModel        string `xml:"MakeModel"`
	VehicleClass     string `xml:"VehicleClass"`
	Co2Emissions     string `xml:"Co2Emissions"`
}

func (r *chAPIResolver) Resolve(ctx context.Context, plate string) (*PlateResult, error) {
	if err := validateCHPlate(plate); err != nil {
		return nil, err
	}

	canton, _ := chExtractCanton(plate)

	apiURL := fmt.Sprintf(
		"https://www.kennzeichenapi.ch/api/reg.asmx/CheckSwitzerland?RegistrationNumber=%s&username=%s",
		url.QueryEscape(plate), url.QueryEscape(r.username),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("CH API request: %w", err)
	}
	req.Header.Set("User-Agent", plateUA)
	req.Header.Set("Accept", "application/xml, text/xml, */*")

	resp, err := r.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: kennzeichenapi.ch unreachable: %v", ErrPlateResolutionUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return nil, fmt.Errorf("CH API: invalid API key")
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return nil, fmt.Errorf("CH API read: %w", err)
	}

	bodyStr := strings.TrimSpace(string(body))

	// Handle known text error responses
	switch {
	case strings.Contains(bodyStr, "Daily limit reached"):
		return nil, fmt.Errorf("%w: CH API daily limit reached — wait 24h or upgrade plan", ErrPlateResolutionUnavailable)
	case strings.Contains(bodyStr, "Missing parameter"):
		return nil, fmt.Errorf("CH API: bad request — %s", bodyStr)
	case strings.Contains(bodyStr, "not found") || strings.Contains(strings.ToLower(bodyStr), "no vehicle"):
		return nil, fmt.Errorf("%w: CH plate %s not found", ErrPlateNotFound, plate)
	}

	// Parse XML
	var data chAPIResponse
	if err := xml.Unmarshal(body, &data); err != nil {
		return nil, fmt.Errorf("CH API parse: %w (body: %.100s)", err, bodyStr)
	}

	if data.CarMake.CurrentTextValue == "" && data.Description == "" {
		return nil, fmt.Errorf("%w: CH plate %s returned no data", ErrPlateNotFound, plate)
	}

	result := &PlateResult{
		Plate:     plate,
		Country:   "CH",
		District:  canton,
		Source:    "kennzeichenapi.ch (ASTRA/FEDRO)",
		FetchedAt: time.Now().UTC(),
	}

	if m := data.CarMake.CurrentTextValue; m != "" {
		result.Make = m
	}
	if m := data.CarModel.CurrentTextValue; m != "" {
		result.Model = m
	}
	// Description is often "Make Model" — fill gaps
	if result.Make == "" && data.Description != "" {
		parts := strings.SplitN(data.Description, " ", 2)
		result.Make = parts[0]
		if len(parts) > 1 {
			result.Model = parts[1]
		}
	}

	if data.RegistrationYear > 1900 {
		t := time.Date(data.RegistrationYear, 1, 1, 0, 0, 0, 0, time.UTC)
		result.FirstRegistration = &t
	}

	result.Transmission = data.Transmission
	result.FuelType = normaliseCHFuel(data.FuelType)
	result.TypeApprovalNumber = data.EuroTypeCode
	result.BodyType = data.BodyStyle
	if data.NumberOfDoors > 0 {
		result.NumberOfDoors = data.NumberOfDoors
	}
	if data.NumberOfSeats > 0 {
		result.NumberOfSeats = data.NumberOfSeats
	}
	if data.EngineSize > 0 {
		result.DisplacementCC = data.EngineSize
	}
	if data.PowerBhp > 0 {
		// Convert bhp → kW (1 bhp ≈ 0.7457 kW)
		result.PowerKW = float64(data.PowerBhp) * 0.7457
		result.PowerCV = int(float64(data.PowerBhp) * 1.01387) // bhp → CV (metric hp)
	}
	if co2 := parseCHCO2(data.Co2Emissions); co2 > 0 {
		result.CO2GPerKm = co2
	}

	result.Partial = result.Make == "" || result.FirstRegistration == nil
	return result, nil
}

func normaliseCHFuel(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "benzin", "petrol", "gasoline", "essence":
		return "Petrol"
	case "diesel":
		return "Diesel"
	case "benzin / elektrisch", "hybrid petrol", "benzin/elektrisch":
		return "Hybrid (Petrol)"
	case "diesel / elektrisch", "hybrid diesel":
		return "Hybrid (Diesel)"
	case "elektrisch", "electric", "batterie":
		return "Electric"
	case "erdgas", "cng":
		return "CNG"
	case "lpg", "autogas":
		return "LPG"
	}
	return s
}

func parseCHCO2(s string) float64 {
	s = strings.TrimSpace(strings.Replace(s, "g/km", "", 1))
	f, _ := strconv.ParseFloat(s, 64)
	return f
}
