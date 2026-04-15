package v14_freshness_test

import (
	"context"
	"testing"
	"time"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v14_freshness"
)

// fixedClock returns a function that always returns the given time.
func fixedClock(t time.Time) func() time.Time { return func() time.Time { return t } }

var now = time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC)

func vehicle(extractedAt time.Time, isArchive bool) *pipeline.Vehicle {
	v := &pipeline.Vehicle{InternalID: "T1", ExtractedAt: extractedAt}
	if isArchive {
		v.Metadata = map[string]string{"is_archive": "true"}
	}
	return v
}

// TestV14_FreshVehicle verifies that a vehicle extracted 1 hour ago passes.
func TestV14_FreshVehicle(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	res, err := val.Validate(context.Background(), vehicle(now.Add(-1*time.Hour), false))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 1-hour-old vehicle, issue: %s", res.Issue)
	}
}

// TestV14_SlightlyStale verifies that a vehicle extracted 48 hours ago is INFO pass.
func TestV14_SlightlyStale(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	res, err := val.Validate(context.Background(), vehicle(now.Add(-48*time.Hour), false))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 48-hour-old vehicle, issue: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for 48h stale, got %s", res.Severity)
	}
}

// TestV14_Stale verifies that a vehicle extracted 5 days ago is WARNING.
func TestV14_Stale(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	res, err := val.Validate(context.Background(), vehicle(now.Add(-5*24*time.Hour), false))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 5-day stale, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for 5-day stale, got %s", res.Severity)
	}
}

// TestV14_VeryStale verifies that a vehicle extracted 10 days ago is CRITICAL.
func TestV14_VeryStale(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	res, err := val.Validate(context.Background(), vehicle(now.Add(-10*24*time.Hour), false))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 10-day stale, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 10-day stale, got %s", res.Severity)
	}
}

// TestV14_Archive verifies that archive vehicles are skipped with INFO.
func TestV14_Archive(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	// Very old extraction but marked as archive.
	res, err := val.Validate(context.Background(), vehicle(now.Add(-365*24*time.Hour), true))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true for archive vehicle, got false")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for archive vehicle, got %s", res.Severity)
	}
}

// TestV14_MissingTimestamp verifies that zero ExtractedAt is INFO (not a failure).
func TestV14_MissingTimestamp(t *testing.T) {
	val := v14_freshness.NewWithClock(fixedClock(now))
	res, err := val.Validate(context.Background(), vehicle(time.Time{}, false))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true for missing timestamp")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for missing timestamp, got %s", res.Severity)
	}
}
