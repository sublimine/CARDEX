package kg_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/kg"
)

// openTestDB opens an in-memory SQLite database and applies the KG schema.
func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("openTestDB: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return database
}

func TestUpsertAndFindByIdentifier(t *testing.T) {
	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Second)

	entity := &kg.DealerEntity{
		DealerID:          "01HMEXAMPLEULID001",
		CanonicalName:     "GARAGE DUPONT AUTOMOBILES",
		NormalizedName:    "garage dupont automobiles",
		CountryCode:       "FR",
		Status:            kg.StatusActive,
		ConfidenceScore:   0.35,
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := graph.UpsertDealer(ctx, entity); err != nil {
		t.Fatalf("UpsertDealer: %v", err)
	}

	identifier := &kg.DealerIdentifier{
		IdentifierID:    "01HMEXAMPLEULID002",
		DealerID:        entity.DealerID,
		IdentifierType:  kg.IdentifierSIRET,
		IdentifierValue: "12345678900014",
		SourceFamily:    "A",
		ValidStatus:     "VALID",
	}
	if err := graph.AddIdentifier(ctx, identifier); err != nil {
		t.Fatalf("AddIdentifier: %v", err)
	}

	// Find by the SIRET we just inserted.
	dealerID, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierSIRET, "12345678900014")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID != entity.DealerID {
		t.Errorf("got dealerID=%q, want %q", dealerID, entity.DealerID)
	}
}

func TestFindByIdentifier_NotFound(t *testing.T) {
	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ctx := context.Background()

	dealerID, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierSIRET, "nonexistent")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if dealerID != "" {
		t.Errorf("expected empty string, got %q", dealerID)
	}
}

func TestAddIdentifier_Idempotent(t *testing.T) {
	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ctx := context.Background()

	now := time.Now().UTC()
	entity := &kg.DealerEntity{
		DealerID:          "01HMEXAMPLEULID003",
		CanonicalName:     "AUTO MARTIN SAS",
		NormalizedName:    "auto martin sas",
		CountryCode:       "FR",
		Status:            kg.StatusActive,
		ConfidenceScore:   0.35,
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := graph.UpsertDealer(ctx, entity); err != nil {
		t.Fatalf("UpsertDealer: %v", err)
	}

	id := &kg.DealerIdentifier{
		IdentifierID:    "01HMEXAMPLEULID004",
		DealerID:        entity.DealerID,
		IdentifierType:  kg.IdentifierSIRET,
		IdentifierValue: "98765432100021",
		SourceFamily:    "A",
		ValidStatus:     "VALID",
	}
	// Insert twice — second call must not return an error (INSERT OR IGNORE).
	if err := graph.AddIdentifier(ctx, id); err != nil {
		t.Fatalf("first AddIdentifier: %v", err)
	}
	if err := graph.AddIdentifier(ctx, id); err != nil {
		t.Fatalf("second AddIdentifier (idempotent): %v", err)
	}
}

func TestAddLocation(t *testing.T) {
	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ctx := context.Background()

	now := time.Now().UTC()
	entity := &kg.DealerEntity{
		DealerID:          "01HMEXAMPLEULID005",
		CanonicalName:     "TEST DEALER",
		NormalizedName:    "test dealer",
		CountryCode:       "FR",
		Status:            kg.StatusActive,
		ConfidenceScore:   0.35,
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := graph.UpsertDealer(ctx, entity); err != nil {
		t.Fatalf("UpsertDealer: %v", err)
	}

	city := "PARIS"
	postal := "75001"
	loc := &kg.DealerLocation{
		LocationID:     "01HMEXAMPLEULID006",
		DealerID:       entity.DealerID,
		IsPrimary:      true,
		CountryCode:    "FR",
		City:           &city,
		PostalCode:     &postal,
		SourceFamilies: "A",
	}
	if err := graph.AddLocation(ctx, loc); err != nil {
		t.Fatalf("AddLocation: %v", err)
	}
}

func TestConfidenceScore(t *testing.T) {
	tests := []struct {
		families []string
		want     float64
	}{
		{[]string{"A"}, 0.35},
		{[]string{"A", "A"}, 0.35},        // duplicate ignored
		{[]string{}, 0.0},
		{[]string{"B"}, 0.15},
		{[]string{"A", "B"}, 0.50},        // Sprint 3: A=0.35 + B=0.15
		{[]string{"A", "B", "C", "D"}, 0.50}, // C/D have no weight yet
	}
	for _, tc := range tests {
		got := kg.ComputeConfidence(tc.families)
		if got != tc.want {
			t.Errorf("ComputeConfidence(%v) = %f, want %f", tc.families, got, tc.want)
		}
	}
}
