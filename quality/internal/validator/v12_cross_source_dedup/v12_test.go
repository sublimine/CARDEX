package v12_cross_source_dedup_test

import (
	"context"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v12_cross_source_dedup"
)

// mockDedupStore implements DedupStore for testing.
type mockDedupStore struct {
	records []*v12_cross_source_dedup.VehicleRecord
}

func (m *mockDedupStore) GetVehiclesByVIN(_ context.Context, _ string) ([]*v12_cross_source_dedup.VehicleRecord, error) {
	return m.records, nil
}

func vehicle(vin, dealerID string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", VIN: vin, DealerID: dealerID}
}

func record(vin, dealerID, sourceURL string) *v12_cross_source_dedup.VehicleRecord {
	return &v12_cross_source_dedup.VehicleRecord{VIN: vin, DealerID: dealerID, SourceURL: sourceURL}
}

// TestV12_UniqueVIN verifies that a VIN with no duplicates passes cleanly.
func TestV12_UniqueVIN(t *testing.T) {
	store := &mockDedupStore{records: nil}
	val := v12_cross_source_dedup.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("WBA3A5C51DF358058", "D1"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for unique VIN, issue: %s", res.Issue)
	}
}

// TestV12_SameDealer_MultiListing verifies two records from same dealer is INFO.
func TestV12_SameDealer_MultiListing(t *testing.T) {
	store := &mockDedupStore{records: []*v12_cross_source_dedup.VehicleRecord{
		record("WBA3A5C51DF358058", "D1", "https://autosite.de/listing/1"),
		record("WBA3A5C51DF358058", "D1", "https://mobile.de/listing/99"),
	}}
	val := v12_cross_source_dedup.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("WBA3A5C51DF358058", "D1"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for same-dealer multi-listing, issue: %s", res.Issue)
	}
}

// TestV12_ThreeDealers_Warning verifies 3 distinct dealers produces a WARNING.
func TestV12_ThreeDealers_Warning(t *testing.T) {
	store := &mockDedupStore{records: []*v12_cross_source_dedup.VehicleRecord{
		record("WBA3A5C51DF358058", "D1", "https://dealer1.de/123"),
		record("WBA3A5C51DF358058", "D2", "https://dealer2.fr/456"),
		record("WBA3A5C51DF358058", "D3", "https://dealer3.es/789"),
	}}
	val := v12_cross_source_dedup.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("WBA3A5C51DF358058", "D4"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 3-dealer duplicate, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for 3-dealer VIN, got %s", res.Severity)
	}
}

// TestV12_SevenDealers_Critical verifies >5 dealers is CRITICAL.
func TestV12_SevenDealers_Critical(t *testing.T) {
	var records []*v12_cross_source_dedup.VehicleRecord
	dealers := []string{"D1", "D2", "D3", "D4", "D5", "D6", "D7"}
	for i, d := range dealers {
		records = append(records, record("WBA3A5C51DF358058", d,
			"https://dealer.example.com/"+string(rune('a'+i))))
	}
	store := &mockDedupStore{records: records}
	val := v12_cross_source_dedup.NewWithStore(store)
	res, err := val.Validate(context.Background(), vehicle("WBA3A5C51DF358058", "D8"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 7-dealer critical, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 7-dealer VIN, got %s", res.Severity)
	}
}
