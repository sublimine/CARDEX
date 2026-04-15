package v01_vin_checksum_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v01_vin_checksum"
)

func v(vin string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", VIN: vin}
}

// TestV01_ValidVIN verifies that a well-known valid VIN passes with confidence 1.0.
func TestV01_ValidVIN(t *testing.T) {
	// 1HGBH41JXMN109186 is a canonical Honda Civic test VIN (check digit X at pos 9).
	val := v01_vin_checksum.New()
	res, err := val.Validate(context.Background(), v("1HGBH41JXMN109186"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for valid VIN, got issue: %s", res.Issue)
	}
	if res.Confidence != 1.0 {
		t.Errorf("want confidence 1.0, got %f", res.Confidence)
	}
	if res.ValidatorID != "V01" {
		t.Errorf("want ID V01, got %s", res.ValidatorID)
	}
}

// TestV01_InvalidCheckDigit verifies that a VIN with a wrong check digit fails CRITICAL.
func TestV01_InvalidCheckDigit(t *testing.T) {
	// Corrupt check digit: change X (pos 9) to A.
	val := v01_vin_checksum.New()
	res, err := val.Validate(context.Background(), v("1HGBH41JAMN109186"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for bad check digit, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want severity CRITICAL, got %s", res.Severity)
	}
	if res.Suggested["VIN"] == "" {
		t.Error("want suggested correction for VIN, got empty")
	}
}

// TestV01_TooShort verifies that a VIN shorter than 17 characters fails.
func TestV01_TooShort(t *testing.T) {
	val := v01_vin_checksum.New()
	res, err := val.Validate(context.Background(), v("1HGBH41J"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for short VIN, got true")
	}
}

// TestV01_ForbiddenCharacters verifies that VINs containing I, O, or Q fail.
func TestV01_ForbiddenCharacters(t *testing.T) {
	val := v01_vin_checksum.New()
	for _, bad := range []string{
		"1HGBI41JXMN109186", // I at pos 5
		"1HGBH41JXMO109186", // O at pos 12
		"1HGBH41JXMQ109186", // Q at pos 12
	} {
		res, err := val.Validate(context.Background(), v(bad))
		if err != nil {
			t.Fatalf("unexpected error for %s: %v", bad, err)
		}
		if res.Pass {
			t.Errorf("want pass=false for forbidden char in %s, got true", bad)
		}
	}
}

// TestV01_AnotherValidVIN verifies a second real-world VIN (BMW).
func TestV01_AnotherValidVIN(t *testing.T) {
	// WBA3A5C51DF358058 — check digit at position 9 is '1' (weighted sum=364, 364 mod 11=1).
	val := v01_vin_checksum.New()
	res, err := val.Validate(context.Background(), v("WBA3A5C51DF358058"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for WBA3A5C50DF358058, issue: %s", res.Issue)
	}
}
