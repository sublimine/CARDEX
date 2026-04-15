package v02_nhtsa_vpic_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v02_nhtsa_vpic"
)

// vpicResult mirrors the NHTSA response shape used in tests.
type vpicResult struct {
	Variable string `json:"Variable"`
	Value    string `json:"Value"`
}

// mockVPIC returns an httptest server that serves a canned vPIC response for
// the given make/model/year. An empty errorText means a clean decode.
func mockVPIC(make_, model string, year int, errorText string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		results := []vpicResult{
			{Variable: "Make", Value: make_},
			{Variable: "Model", Value: model},
			{Variable: "Model Year", Value: fmt.Sprintf("%d", year)},
			{Variable: "Fuel Type - Primary", Value: "Gasoline"},
		}
		if errorText != "" {
			results = append(results, vpicResult{Variable: "Error Text", Value: errorText})
		} else {
			results = append(results, vpicResult{
				Variable: "Error Text",
				Value:    "0 - VIN decoded clean. Check Digit (9th position) is correct",
			})
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"Count":   len(results),
			"Results": results,
		})
	}))
}

// TestV02_BMW_Match verifies that a BMW VIN whose make/model match NHTSA passes.
func TestV02_BMW_Match(t *testing.T) {
	srv := mockVPIC("BMW", "3 Series", 2021, "")
	defer srv.Close()

	val := v02_nhtsa_vpic.NewWithClient(srv.Client(), srv.URL+"/%s?format=json")
	vehicle := &pipeline.Vehicle{
		InternalID: "V1",
		VIN:        "WBA3A5C50DF358058",
		Make:       "BMW",
		Model:      "3 Series",
		Year:       2021,
	}

	res, err := val.Validate(context.Background(), vehicle)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for matching BMW, got issue: %s", res.Issue)
	}
	if res.Evidence["nhtsa_make"] != "BMW" {
		t.Errorf("want evidence nhtsa_make=BMW, got %q", res.Evidence["nhtsa_make"])
	}
}

// TestV02_Toyota_Match verifies a Toyota VIN with matching data passes.
func TestV02_Toyota_Match(t *testing.T) {
	srv := mockVPIC("TOYOTA", "Corolla", 2019, "")
	defer srv.Close()

	val := v02_nhtsa_vpic.NewWithClient(srv.Client(), srv.URL+"/%s?format=json")
	vehicle := &pipeline.Vehicle{
		InternalID: "V2",
		VIN:        "1HGBH41JXMN109186", // any 17-char VIN
		Make:       "Toyota",
		Model:      "Corolla",
		Year:       2019,
	}

	res, err := val.Validate(context.Background(), vehicle)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for matching Toyota, issue: %s", res.Issue)
	}
}

// TestV02_VINNotDecodable verifies that NHTSA decode errors produce an INFO result,
// not a failure (many non-US VINs are valid but unknown to NHTSA).
func TestV02_VINNotDecodable(t *testing.T) {
	srv := mockVPIC("", "", 0, "11 - Manufacturer is not registered with NHTSA for VIN decoding")
	defer srv.Close()

	val := v02_nhtsa_vpic.NewWithClient(srv.Client(), srv.URL+"/%s?format=json")
	vehicle := &pipeline.Vehicle{
		InternalID: "V3",
		VIN:        "VF1AA000551512345", // French VIN, unknown to NHTSA
		Make:       "Renault",
		Year:       2020,
	}

	res, err := val.Validate(context.Background(), vehicle)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Non-decodable VIN should not be a failure.
	if !res.Pass {
		t.Errorf("want pass=true for non-decodable VIN, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want severity INFO for non-decodable, got %s", res.Severity)
	}
}

// TestV02_APIDown_Graceful verifies that an unreachable NHTSA API does not
// fail the vehicle (recorded as INFO, not blocking).
func TestV02_APIDown_Graceful(t *testing.T) {
	// Use a URL that refuses connection.
	val := v02_nhtsa_vpic.NewWithClient(
		&http.Client{},
		"http://127.0.0.1:1/%s?format=json", // port 1 always refuses
	)
	vehicle := &pipeline.Vehicle{
		InternalID: "V4",
		VIN:        "WBA3A5C50DF358058",
		Make:       "BMW",
	}

	res, err := val.Validate(context.Background(), vehicle)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	// API down → graceful INFO, not a blocking failure.
	if !res.Pass {
		t.Errorf("want pass=true when API is down, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want severity INFO when API down, got %s", res.Severity)
	}
}

// TestV02_MakeMismatch verifies that a make mismatch produces a WARNING and suggested fix.
func TestV02_MakeMismatch(t *testing.T) {
	srv := mockVPIC("HONDA", "Civic", 2020, "")
	defer srv.Close()

	val := v02_nhtsa_vpic.NewWithClient(srv.Client(), srv.URL+"/%s?format=json")
	vehicle := &pipeline.Vehicle{
		InternalID: "V5",
		VIN:        "1HGBH41JXMN109186",
		Make:       "Toyota", // wrong make
		Model:      "Civic",
		Year:       2020,
	}

	res, err := val.Validate(context.Background(), vehicle)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for make mismatch, got true")
	}
	if res.Suggested["Make"] != "HONDA" {
		t.Errorf("want Suggested[Make]=HONDA, got %q", res.Suggested["Make"])
	}
}
