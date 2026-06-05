package restparams

import (
	"net/url"
	"strings"
	"testing"
)

func mustValues(t *testing.T, raw string) url.Values {
	t.Helper()
	v, err := url.ParseQuery(raw)
	if err != nil {
		t.Fatalf("parse query: %v", err)
	}
	return v
}

func TestParseFilterRequiresMakeModel(t *testing.T) {
	if _, err := ParseFilter(mustValues(t, "make=BMW")); err == nil {
		t.Error("expected error when model missing")
	}
	if _, err := ParseFilter(mustValues(t, "model=320d")); err == nil {
		t.Error("expected error when make missing")
	}
}

func TestParseFilterExactYearExpands(t *testing.T) {
	f, err := ParseFilter(mustValues(t, "make=BMW&model=320d&year=2020"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if f.YearMin != 2020 || f.YearMax != 2020 {
		t.Errorf("year=2020 → min=%d max=%d, want 2020/2020", f.YearMin, f.YearMax)
	}
}

func TestParseFilterYearRange(t *testing.T) {
	f, err := ParseFilter(mustValues(t, "make=BMW&model=320d&year_min=2018&year_max=2021"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if f.YearMin != 2018 || f.YearMax != 2021 {
		t.Errorf("got min=%d max=%d, want 2018/2021", f.YearMin, f.YearMax)
	}
}

func TestParseFilterRejectsInvertedRanges(t *testing.T) {
	if _, err := ParseFilter(mustValues(t, "make=BMW&model=x&year_min=2021&year_max=2018")); err == nil {
		t.Error("expected error for year_min > year_max")
	}
	if _, err := ParseFilter(mustValues(t, "make=BMW&model=x&mileage_min=100000&mileage_max=50000")); err == nil {
		t.Error("expected error for mileage_min > mileage_max")
	}
}

func TestParseFilterCountriesValidation(t *testing.T) {
	f, err := ParseFilter(mustValues(t, "make=BMW&model=x&countries=DE,es,NL"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(f.Countries) != 3 || f.Countries[0] != "DE" || f.Countries[1] != "ES" {
		t.Errorf("countries = %v, want [DE ES NL]", f.Countries)
	}
	if _, err := ParseFilter(mustValues(t, "make=BMW&model=x&countries=DE,XX")); err == nil {
		t.Error("expected error for unsupported country XX")
	}
}

func TestParseFilterRejectsOverlongFields(t *testing.T) {
	long := strings.Repeat("A", 65)
	if _, err := ParseFilter(mustValues(t, "make="+long+"&model=320d")); err == nil {
		t.Error("expected error for over-long make")
	}
	if _, err := ParseFilter(mustValues(t, "make=BMW&model=320d&fuel="+long)); err == nil {
		t.Error("expected error for over-long fuel")
	}
}

func TestParseLimitBounds(t *testing.T) {
	v := mustValues(t, "max_results=500")
	n, err := ParseLimit(v, "max_results", 20, 100)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if n != 100 {
		t.Errorf("limit clamped to %d, want 100", n)
	}
	if _, err := ParseLimit(mustValues(t, "max_results=-1"), "max_results", 20, 100); err == nil {
		t.Error("expected error for negative limit")
	}
}
