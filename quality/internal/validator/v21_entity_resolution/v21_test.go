package v21_entity_resolution_test

import (
	"context"
	"database/sql"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v21_entity_resolution"
)

// openMemDB opens an in-memory SQLite database for testing.
func openMemDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:?_journal_mode=WAL")
	if err != nil {
		t.Fatalf("open mem db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func vehicle(dealerID, country, dealerName, city string) *pipeline.Vehicle {
	return &pipeline.Vehicle{
		InternalID:    "V_" + dealerID,
		DealerID:      dealerID,
		SourceCountry: country,
		Metadata: map[string]string{
			"dealer_name": dealerName,
			"dealer_city": city,
		},
	}
}

// TestV21_SameEntity_DE verifies that two representations of the same German
// dealer resolve to the same canonical entity.
func TestV21_SameEntity_DE(t *testing.T) {
	db := openMemDB(t)
	v, err := v21_entity_resolution.NewWithDB(db, v21_entity_resolution.Config{
		Threshold: 0.75, // TF-IDF needs a lower threshold than mpnet
	})
	if err != nil {
		t.Fatalf("NewWithDB: %v", err)
	}

	ctx := context.Background()

	// Insert canonical entity first.
	r1, err := v.Validate(ctx, vehicle("DEALER_DE_001", "DE", "BMW Autohaus GmbH München", "München"))
	if err != nil {
		t.Fatalf("validate 1: %v", err)
	}
	if r1.Evidence["entity_status"] != "unique" {
		t.Errorf("first insert should be 'unique', got %q", r1.Evidence["entity_status"])
	}

	// Same dealer, name variation: "Autohaus München BMW GmbH"
	r2, err := v.Validate(ctx, vehicle("DEALER_DE_001b", "DE", "Autohaus München BMW GmbH", "München"))
	if err != nil {
		t.Fatalf("validate 2: %v", err)
	}
	// TF-IDF over char 3-grams: "bmw autohaus gmbh münchen" ≃ "autohaus münchen bmw gmbh"
	// They share the same n-grams → high cosine similarity.
	if r2.Evidence["entity_status"] != "merged" {
		t.Errorf("similar dealer should be 'merged', got %q (sim=%s)",
			r2.Evidence["entity_status"], r2.Evidence["cosine_similarity"])
	}
	if r2.Suggested["canonical_dealer_id"] != "DEALER_DE_001" {
		t.Errorf("canonical should be DEALER_DE_001, got %q", r2.Suggested["canonical_dealer_id"])
	}
}

// TestV21_SameEntity_FR verifies French dealer resolution.
func TestV21_SameEntity_FR(t *testing.T) {
	db := openMemDB(t)
	v, err := v21_entity_resolution.NewWithDB(db, v21_entity_resolution.Config{Threshold: 0.75})
	if err != nil {
		t.Fatalf("NewWithDB: %v", err)
	}

	ctx := context.Background()
	v.Validate(ctx, vehicle("FR_RENAULT_001", "FR", "Garage Renault Lyon Centre", "Lyon")) //nolint
	r, err := v.Validate(ctx, vehicle("FR_RENAULT_001b", "FR", "Renault Lyon Centre Garage", "Lyon"))
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if r.Evidence["entity_status"] != "merged" {
		t.Errorf("want 'merged' for FR same-entity, got %q", r.Evidence["entity_status"])
	}
}

// TestV21_SameEntity_ES verifies Spanish dealer resolution.
func TestV21_SameEntity_ES(t *testing.T) {
	db := openMemDB(t)
	v, err := v21_entity_resolution.NewWithDB(db, v21_entity_resolution.Config{Threshold: 0.75})
	if err != nil {
		t.Fatalf("NewWithDB: %v", err)
	}

	ctx := context.Background()
	v.Validate(ctx, vehicle("ES_SEAT_001", "ES", "Seat Concesionario Madrid Sur", "Madrid")) //nolint
	r, err := v.Validate(ctx, vehicle("ES_SEAT_001b", "ES", "Concesionario Madrid Sur SEAT", "Madrid"))
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if r.Evidence["entity_status"] != "merged" {
		t.Errorf("want 'merged' for ES same-entity, got %q", r.Evidence["entity_status"])
	}
}

// TestV21_DifferentEntities_NotMerged verifies that two genuinely different
// dealers with similar-sounding names are NOT merged.
func TestV21_DifferentEntities_NotMerged(t *testing.T) {
	db := openMemDB(t)
	// Use high threshold to prevent false positives between different dealers.
	v, err := v21_entity_resolution.NewWithDB(db, v21_entity_resolution.Config{Threshold: 0.92})
	if err != nil {
		t.Fatalf("NewWithDB: %v", err)
	}

	ctx := context.Background()
	// Two different German dealers that happen to both be BMW dealers.
	v.Validate(ctx, vehicle("DEALER_DE_A", "DE", "BMW Autohaus GmbH Berlin", "Berlin"))    //nolint
	r, err := v.Validate(ctx, vehicle("DEALER_DE_B", "DE", "BMW Autohaus GmbH Hamburg", "Hamburg"))
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	// Berlin ≠ Hamburg → different n-grams → below 0.92 threshold.
	if r.Evidence["entity_status"] == "merged" {
		t.Errorf("different city dealers must NOT be merged (Berlin vs Hamburg)")
	}
}

// TestV21_NilDB_NoIndex ensures V21 gracefully handles nil index.
func TestV21_NilDB_NoIndex(t *testing.T) {
	v := v21_entity_resolution.New()
	r, err := v.Validate(context.Background(), vehicle("D1", "DE", "Test Autohaus", "Berlin"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if r.Evidence["index"] == "" {
		t.Error("want no-op index note in evidence, got nothing")
	}
	if !r.Pass {
		t.Error("want Pass=true even with nil index")
	}
}

// TestTFIDFEmbedder_CosineSimilarity verifies the pure-Go embedder produces
// sensible similarity scores.
func TestTFIDFEmbedder_CosineSimilarity(t *testing.T) {
	emb := &v21_entity_resolution.TFIDFEmbedder{}
	ctx := context.Background()

	v1, _ := emb.Embed(ctx, "BMW Autohaus GmbH München")
	v2, _ := emb.Embed(ctx, "Autohaus München BMW GmbH")
	v3, _ := emb.Embed(ctx, "Renault Garage Lyon France")

	simSame := v21_entity_resolution.CosineSimilarity(v1, v2)
	simDiff := v21_entity_resolution.CosineSimilarity(v1, v3)

	if simSame <= simDiff {
		t.Errorf("same dealer should have higher similarity: same=%.3f diff=%.3f", simSame, simDiff)
	}
	if simSame < 0.7 {
		t.Errorf("same dealer cosine too low: %.3f (expected > 0.7)", simSame)
	}
}

// TestV21_Priority verifies validator interface methods.
func TestV21_Priority(t *testing.T) {
	v := v21_entity_resolution.New()
	if v.ID() != "V21" {
		t.Errorf("want ID=V21, got %q", v.ID())
	}
	if v.Severity() != "INFO" {
		t.Errorf("want Severity=INFO, got %q", v.Severity())
	}
}
