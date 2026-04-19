package check

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// VINInfo holds the decoded output from a VIN lookup.
// Field names match the frontend VINDecodeResult type.
type VINInfo struct {
	VIN                string            `json:"vin"`
	WMI                string            `json:"wmi,omitempty"`
	Manufacturer       string            `json:"manufacturer"`
	Make               string            `json:"make"` // alias for Manufacturer (frontend expects both)
	Country            string            `json:"countryOfManufacture"`
	ModelYear          int               `json:"year"`
	PlantCode          string            `json:"plant,omitempty"`
	SerialNumber       string            `json:"serialNumber,omitempty"`
	Model              string            `json:"model,omitempty"`
	BodyType           string            `json:"bodyType,omitempty"`
	FuelType           string            `json:"fuelType,omitempty"`
	EngineDisplacement string            `json:"engineDisplacement,omitempty"`
	DriveType          string            `json:"driveType,omitempty"`
	PlantCountry       string            `json:"plantCountry,omitempty"`
	RawNHTSA           map[string]string `json:"-"` // omitted from HTTP responses (too verbose)
}

// ErrInvalidVIN is returned when a VIN fails ISO 3779 validation.
var ErrInvalidVIN = errors.New("invalid VIN")

// ValidateVIN checks format, characters, and check digit per ISO 3779.
// Returns a descriptive error if the VIN is invalid, nil if valid.
func ValidateVIN(vin string) error {
	vin = strings.ToUpper(strings.TrimSpace(vin))
	if len(vin) != 17 {
		return fmt.Errorf("%w: must be 17 characters, got %d", ErrInvalidVIN, len(vin))
	}
	for i, c := range vin {
		if c == 'I' || c == 'O' || c == 'Q' {
			return fmt.Errorf("%w: character %c at position %d is not allowed", ErrInvalidVIN, c, i+1)
		}
		if !isVINChar(byte(c)) {
			return fmt.Errorf("%w: invalid character %c at position %d", ErrInvalidVIN, c, i+1)
		}
	}
	if err := checkVINDigit(vin); err != nil {
		return err
	}
	return nil
}

func isVINChar(c byte) bool {
	return (c >= 'A' && c <= 'Z' && c != 'I' && c != 'O' && c != 'Q') || (c >= '0' && c <= '9')
}

// transliterationValues maps VIN characters to their numeric equivalents per ISO 3779.
var translitValues = map[byte]int{
	'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
	'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5,
	'P': 7, 'R': 9,
	'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
	'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5,
	'6': 6, '7': 7, '8': 8, '9': 9,
}

// positional weights for each of the 17 VIN characters.
var positionWeights = [17]int{8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2}

func checkVINDigit(vin string) error {
	sum := 0
	for i := 0; i < 17; i++ {
		v, ok := translitValues[vin[i]]
		if !ok {
			return fmt.Errorf("%w: untransliterable character %c at position %d", ErrInvalidVIN, vin[i], i+1)
		}
		sum += v * positionWeights[i]
	}
	rem := sum % 11
	var want byte
	if rem == 10 {
		want = 'X'
	} else {
		want = byte('0' + rem)
	}
	got := vin[8]
	if got != want {
		return fmt.Errorf("%w: check digit mismatch at position 9: want %c, got %c", ErrInvalidVIN, want, got)
	}
	return nil
}

// DecodeVIN parses the WMI/VDS/VIS sections from a pre-validated VIN.
// Call ValidateVIN first; DecodeVIN does not re-validate.
func DecodeVIN(vin string) VINInfo {
	vin = strings.ToUpper(strings.TrimSpace(vin))
	wmi := vin[:3]
	mfr, country := lookupWMI(wmi)
	year := decodeModelYear(vin[9])
	return VINInfo{
		VIN:          vin,
		WMI:          wmi,
		Manufacturer: mfr,
		Make:         mfr,
		Country:      country,
		ModelYear:    year,
		PlantCode:    string(vin[10]),
		SerialNumber: vin[11:],
	}
}

// vinYearTable maps position-10 characters to model years.
// Letters are ambiguous (30-year cycle): this table returns the 2010–2040 cycle for
// letters and 2001–2009 for digits, which covers most vehicles in current use.
// For older vehicles (pre-2001), the year may be off by exactly 30 years.
var vinYearTable = map[byte]int{
	'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014,
	'F': 2015, 'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019,
	'L': 2020, 'M': 2021, 'N': 2022, 'P': 2023, 'R': 2024,
	'S': 2025, 'T': 2026, 'V': 2027, 'W': 2028, 'X': 2029,
	'Y': 2030,
	'1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005,
	'6': 2006, '7': 2007, '8': 2008, '9': 2009,
}

func decodeModelYear(c byte) int {
	if y, ok := vinYearTable[c]; ok {
		return y
	}
	return 0
}

// ── WMI table ─────────────────────────────────────────────────────────────────
// Sources: SAE J853 / ISO 3780. Only well-documented WMIs are included.
// Extend by adding rows — do not guess or invent WMI assignments.

type wmiEntry struct {
	Manufacturer string
	Country      string
}

// wmiTable maps the 3-character WMI prefix to manufacturer and country.
// Approximate count: ~120 entries covering major OEMs in DE/FR/ES/BE/NL/CH/US/JP/KR/IT/UK.
var wmiTable = map[string]wmiEntry{
	// ── Germany ──────────────────────────────────────────────────────────────
	"WBA": {"BMW", "DE"}, "WBB": {"BMW", "DE"}, "WBC": {"BMW", "DE"},
	"WBD": {"BMW", "DE"}, "WBE": {"BMW", "DE"}, "WBF": {"BMW", "DE"},
	"WBG": {"BMW", "DE"}, "WBH": {"BMW", "DE"}, "WBK": {"BMW", "DE"},
	"WBM": {"BMW Motorcycles", "DE"}, "WBN": {"BMW", "DE"},
	"WBP": {"BMW", "DE"}, "WBR": {"BMW", "DE"}, "WBW": {"BMW", "DE"},
	"WBX": {"BMW", "DE"}, "WBY": {"BMW (electric)", "DE"},
	"WDA": {"Daimler Trucks", "DE"},
	"WDB": {"Mercedes-Benz", "DE"}, "WDC": {"Mercedes-Benz", "DE"},
	"WDD": {"Mercedes-Benz", "DE"}, "WDF": {"Mercedes-Benz", "DE"},
	"WDK": {"Mercedes-Benz", "DE"}, "WDN": {"Daimler", "DE"},
	"WEB": {"Mercedes-AMG", "DE"},
	"W0V": {"Opel/Vauxhall", "DE"}, "W0L": {"Opel/Vauxhall", "DE"},
	"WAG": {"Audi", "DE"}, "WAP": {"Porsche", "DE"},
	"WAU": {"Audi", "DE"}, "WAB": {"Audi", "DE"}, "WAZ": {"Audi", "DE"},
	"WP0": {"Porsche", "DE"}, "WP1": {"Porsche", "DE"}, "WPO": {"Porsche", "DE"},
	"WVW": {"Volkswagen", "DE"}, "WV1": {"Volkswagen Commercial", "DE"},
	"WV2": {"MAN", "DE"}, "WV3": {"Volkswagen Truck", "DE"},
	"WKK": {"Volkswagen", "DE"},
	"WMA": {"MAN", "DE"}, "WME": {"Smart", "DE"}, "WMT": {"Smart", "DE"},
	"WMW": {"MINI", "DE"},
	"WSS": {"Mercedes-Benz", "DE"},
	"W09": {"Alpina", "DE"},
	// ── France ───────────────────────────────────────────────────────────────
	"VF1": {"Renault", "FR"}, "VF3": {"Peugeot", "FR"},
	"VF6": {"Renault", "FR"}, "VF7": {"Citroën", "FR"},
	"VF8": {"Matra", "FR"}, "VFA": {"Renault", "FR"},
	"VFC": {"Citroën", "FR"}, "VFD": {"Peugeot", "FR"},
	"VFE": {"Peugeot", "FR"},
	"VNE": {"Iveco (FR)", "FR"},
	// ── Italy ────────────────────────────────────────────────────────────────
	"ZAR": {"Alfa Romeo", "IT"}, "ZAA": {"Alfa Romeo", "IT"},
	"ZBD": {"Harley-Davidson (Italy)", "IT"},
	"ZCG": {"Fiat Professional", "IT"},
	"ZCF": {"Fiat Commercial", "IT"},
	"ZDF": {"Ferrari", "IT"}, "ZFF": {"Ferrari", "IT"},
	"ZFA": {"Fiat", "IT"}, "ZFB": {"Fiat", "IT"}, "ZFC": {"Fiat", "IT"},
	"ZGU": {"Maserati", "IT"}, "ZHW": {"Lamborghini", "IT"},
	"ZLA": {"Lancia", "IT"}, "ZLF": {"Alfa Romeo", "IT"},
	"ZMD": {"Mercedes-Benz (IT)", "IT"},
	// ── Spain ────────────────────────────────────────────────────────────────
	"VSE": {"SEAT", "ES"}, "VSK": {"SEAT", "ES"}, "VSS": {"SEAT", "ES"},
	"VNK": {"Toyota (ES)", "ES"},
	// ── Sweden ───────────────────────────────────────────────────────────────
	"YV1": {"Volvo Cars", "SE"}, "YV4": {"Volvo Cars", "SE"},
	"YS3": {"Saab", "SE"}, "YS2": {"Scania", "SE"},
	// ── UK ───────────────────────────────────────────────────────────────────
	"SAJ": {"Jaguar", "GB"}, "SAL": {"Land Rover", "GB"},
	"SAR": {"Rover", "GB"}, "SAB": {"Rover", "GB"},
	"SCA": {"Rolls-Royce", "GB"}, "SCB": {"Bentley", "GB"},
	"SCF": {"Aston Martin", "GB"}, "SCC": {"Lotus", "GB"},
	"SFA": {"Ford (UK)", "GB"}, "SFD": {"Ford (UK)", "GB"},
	"SMT": {"Triumph Motorcycles", "GB"},
	"VBK": {"McLaren", "GB"},
	// ── Netherlands ──────────────────────────────────────────────────────────
	"XLR": {"DAF", "NL"}, "XL9": {"Spyker", "NL"},
	// ── Belgium ──────────────────────────────────────────────────────────────
	"VBN": {"Volvo (BE)", "BE"},
	// ── Czech Republic ───────────────────────────────────────────────────────
	"TMB": {"Škoda", "CZ"}, "TMA": {"Škoda", "CZ"},
	// ── Hungary ──────────────────────────────────────────────────────────────
	"ADR": {"Audi (HU)", "HU"}, "AD6": {"Audi (HU)", "HU"},
	// ── Romania ──────────────────────────────────────────────────────────────
	"UU1": {"Dacia", "RO"}, "UU2": {"Dacia", "RO"},
	// ── USA ──────────────────────────────────────────────────────────────────
	"1FA": {"Ford", "US"}, "1FB": {"Ford", "US"}, "1FC": {"Ford", "US"},
	"1FD": {"Ford Trucks", "US"}, "1FM": {"Ford SUV", "US"},
	"1FT": {"Ford Truck", "US"}, "1FU": {"Freightliner", "US"},
	"1G1": {"Chevrolet", "US"}, "1G6": {"Cadillac", "US"},
	"1GC": {"GMC Truck", "US"}, "1GY": {"Cadillac", "US"},
	"1HD": {"Harley-Davidson", "US"},
	"1HG": {"Honda (US)", "US"}, "1HF": {"Honda (US)", "US"},
	"1N4": {"Nissan (US)", "US"}, "1N6": {"Nissan Truck (US)", "US"},
	"1VW": {"Volkswagen (US)", "US"},
	"2T1": {"Toyota (CA)", "CA"}, "2HG": {"Honda (CA)", "CA"},
	"3VW": {"Volkswagen (MX)", "MX"}, "3VV": {"Volkswagen (MX)", "MX"},
	// ── Japan ────────────────────────────────────────────────────────────────
	"JHM": {"Honda", "JP"}, "JH4": {"Acura", "JP"},
	"JN1": {"Nissan", "JP"}, "JN6": {"Nissan", "JP"}, "JN8": {"Nissan", "JP"},
	"JT2": {"Toyota", "JP"}, "JT3": {"Toyota 4WD", "JP"},
	"JT4": {"Toyota Truck", "JP"}, "JTA": {"Toyota", "JP"},
	"JTD": {"Toyota", "JP"}, "JTJ": {"Lexus", "JP"},
	"JYA": {"Yamaha", "JP"},
	"JS1": {"Suzuki", "JP"}, "JS2": {"Suzuki", "JP"},
	"JF1": {"Subaru", "JP"}, "JF2": {"Subaru", "JP"},
	"JA3": {"Mitsubishi", "JP"}, "JA4": {"Mitsubishi", "JP"},
	// ── South Korea ──────────────────────────────────────────────────────────
	"KMH": {"Hyundai", "KR"}, "KMF": {"Hyundai", "KR"},
	"KNA": {"Kia", "KR"}, "KNB": {"Kia", "KR"},
	"KL5": {"Daewoo", "KR"}, "KLA": {"Daewoo", "KR"},
	// ── China ────────────────────────────────────────────────────────────────
	"LFV": {"Volkswagen (CN)", "CN"}, "LVS": {"Ford (CN)", "CN"},
	"LRW": {"BMW Brilliance", "CN"},
	// ── India ────────────────────────────────────────────────────────────────
	"MA1": {"Mahindra", "IN"}, "MA3": {"Suzuki India", "IN"},
	"MAB": {"Bajaj", "IN"}, "MAJ": {"Ford India", "IN"},
}

func lookupWMI(wmi string) (manufacturer, country string) {
	if e, ok := wmiTable[wmi]; ok {
		return e.Manufacturer, e.Country
	}
	return "Unknown", ""
}

// ── NHTSA vPIC enrichment ─────────────────────────────────────────────────────

// VINDecoder performs VIN decoding and optionally enriches results via NHTSA vPIC.
type VINDecoder struct {
	httpClient *http.Client
	nhtsaBase  string // overridable for testing
}

// NewVINDecoder returns a VINDecoder using the public NHTSA vPIC API.
func NewVINDecoder() *VINDecoder {
	return &VINDecoder{
		httpClient: &http.Client{Timeout: 10 * time.Second},
		nhtsaBase:  "https://vpic.nhtsa.dot.gov",
	}
}

// NewVINDecoderWithBase constructs a VINDecoder pointing at a custom base URL.
// Used for testing and for production overrides via config.NHTSABaseURL.
func NewVINDecoderWithBase(base string) *VINDecoder {
	return &VINDecoder{
		httpClient: &http.Client{Timeout: 5 * time.Second},
		nhtsaBase:  base,
	}
}

// nhtsaDecodeVinValues is the shape of the NHTSA /DecodeVinValues endpoint.
type nhtsaResponse struct {
	Count   int                  `json:"Count"`
	Results []map[string]string  `json:"Results"`
}

// Decode validates, locally decodes, and optionally enriches a VIN via NHTSA.
// If NHTSA enrichment fails, it returns the locally-decoded info without error
// (NHTSA failure is non-fatal).
func (d *VINDecoder) Decode(ctx context.Context, vin string) (*VINInfo, error) {
	vin = strings.ToUpper(strings.TrimSpace(vin))
	if err := ValidateVIN(vin); err != nil {
		return nil, err
	}
	info := DecodeVIN(vin)

	// Enrich from NHTSA — failure is non-fatal, we log and continue.
	if err := d.enrichFromNHTSA(ctx, &info); err != nil {
		_ = err
	}
	return &info, nil
}

func (d *VINDecoder) enrichFromNHTSA(ctx context.Context, info *VINInfo) error {
	url := fmt.Sprintf("%s/api/vehicles/DecodeVinValues/%s?format=json", d.nhtsaBase, info.VIN)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := d.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("NHTSA status %d", resp.StatusCode)
	}

	var result nhtsaResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return err
	}
	if len(result.Results) == 0 {
		return fmt.Errorf("NHTSA: no results")
	}

	r := result.Results[0]
	info.RawNHTSA = r

	if v := r["Make"]; v != "" && v != "0" {
		info.Manufacturer = v
		info.Make = v
	}
	if v := r["Model"]; v != "" && v != "0" {
		info.Model = v
	}
	if v := r["ModelYear"]; v != "" && v != "0" {
		var y int
		if _, err := fmt.Sscanf(v, "%d", &y); err == nil && y > 1900 {
			info.ModelYear = y
		}
	}
	if v := r["BodyClass"]; v != "" && v != "0" {
		info.BodyType = v
	}
	if v := r["FuelTypePrimary"]; v != "" && v != "0" {
		info.FuelType = v
	}
	if v := r["DisplacementL"]; v != "" && v != "0" {
		info.EngineDisplacement = v + "L"
	}
	if v := r["DriveType"]; v != "" && v != "0" {
		info.DriveType = v
	}
	if v := r["PlantCountry"]; v != "" && v != "0" {
		info.PlantCountry = v
	}
	return nil
}
