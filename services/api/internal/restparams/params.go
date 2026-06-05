// Package restparams parses and validates the shared query parameters used by
// the market-price and arbitrage endpoints into a store.Filter.
package restparams

import (
	"fmt"
	"net/url"
	"strconv"
	"strings"

	"cardex.eu/api/internal/store"
)

// SupportedCountries is the set of ISO-3166-1 alpha-2 countries CARDEX covers.
var SupportedCountries = map[string]bool{
	"DE": true, "FR": true, "ES": true, "NL": true, "BE": true, "CH": true,
}

// maxFieldLen bounds free-text make/model/fuel so a crafted value cannot force
// an expensive full-table ILIKE scan.
const maxFieldLen = 64

// ParseFilter builds a store.Filter from query parameters. make and model are
// required; everything else is optional. Returns a client-facing error message
// suitable for a 400 response.
func ParseFilter(q url.Values) (store.Filter, error) {
	var f store.Filter

	f.Make = strings.TrimSpace(q.Get("make"))
	f.Model = strings.TrimSpace(q.Get("model"))
	if f.Make == "" || f.Model == "" {
		return f, fmt.Errorf("both 'make' and 'model' query parameters are required")
	}
	if len(f.Make) > maxFieldLen || len(f.Model) > maxFieldLen {
		return f, fmt.Errorf("'make' and 'model' must be at most %d characters", maxFieldLen)
	}

	// Year: explicit min/max take precedence over exact 'year'.
	yearMin, err := parseInt(q, "year_min")
	if err != nil {
		return f, err
	}
	yearMax, err := parseInt(q, "year_max")
	if err != nil {
		return f, err
	}
	if yearMin == 0 && yearMax == 0 {
		year, err := parseInt(q, "year")
		if err != nil {
			return f, err
		}
		yearMin, yearMax = year, year
	}
	if yearMin != 0 && yearMax != 0 && yearMin > yearMax {
		return f, fmt.Errorf("year_min (%d) cannot exceed year_max (%d)", yearMin, yearMax)
	}
	f.YearMin, f.YearMax = yearMin, yearMax

	f.Fuel = strings.TrimSpace(q.Get("fuel"))
	if len(f.Fuel) > maxFieldLen {
		return f, fmt.Errorf("'fuel' must be at most %d characters", maxFieldLen)
	}

	if f.MileageMin, err = parseInt(q, "mileage_min"); err != nil {
		return f, err
	}
	if f.MileageMax, err = parseInt(q, "mileage_max"); err != nil {
		return f, err
	}
	if f.MileageMin != 0 && f.MileageMax != 0 && f.MileageMin > f.MileageMax {
		return f, fmt.Errorf("mileage_min (%d) cannot exceed mileage_max (%d)", f.MileageMin, f.MileageMax)
	}

	countries, err := parseCountries(q.Get("countries"))
	if err != nil {
		return f, err
	}
	f.Countries = countries

	return f, nil
}

// parseInt reads a non-negative integer parameter; empty returns 0.
func parseInt(q url.Values, key string) (int, error) {
	raw := strings.TrimSpace(q.Get(key))
	if raw == "" {
		return 0, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer, got %q", key, raw)
	}
	if n < 0 {
		return 0, fmt.Errorf("%s must be non-negative, got %d", key, n)
	}
	return n, nil
}

// parseCountries splits, upper-cases and validates a CSV country list.
func parseCountries(raw string) ([]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		code := strings.ToUpper(strings.TrimSpace(p))
		if code == "" {
			continue
		}
		if !SupportedCountries[code] {
			return nil, fmt.Errorf("unsupported country %q; supported: DE, FR, ES, NL, BE, CH", code)
		}
		out = append(out, code)
	}
	return out, nil
}

// ParsePositiveFloat reads an optional positive float parameter, returning def
// when empty.
func ParsePositiveFloat(q url.Values, key string, def float64) (float64, error) {
	raw := strings.TrimSpace(q.Get(key))
	if raw == "" {
		return def, nil
	}
	f, err := strconv.ParseFloat(raw, 64)
	if err != nil || f < 0 {
		return 0, fmt.Errorf("%s must be a non-negative number, got %q", key, raw)
	}
	return f, nil
}

// ParseLimit reads an optional positive integer bounded by max, returning def
// when empty.
func ParseLimit(q url.Values, key string, def, max int) (int, error) {
	raw := strings.TrimSpace(q.Get(key))
	if raw == "" {
		return def, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer, got %q", key, raw)
	}
	if n > max {
		n = max
	}
	return n, nil
}
