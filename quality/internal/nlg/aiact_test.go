package nlg_test

import (
	"testing"
	"time"

	"cardex.eu/quality/internal/nlg"
)

// TestAIGeneratedMetadata_ValidateOK verifies that a fully populated metadata
// struct passes validation.
func TestAIGeneratedMetadata_ValidateOK(t *testing.T) {
	m := &nlg.AIGeneratedMetadata{
		IsAIGenerated: true,
		Model:         "llama-3.2-3b-instruct",
		ModelVersion:  "Q4_K_M",
		GeneratedAt:   time.Now().UTC(),
		PromptHash:    nlg.PromptHash("BMW 320d 2020 DE"),
		Language:      "de",
	}
	if err := m.Validate(); err != nil {
		t.Fatalf("expected valid metadata, got error: %v", err)
	}
}

// TestAIGeneratedMetadata_ValidateNil verifies nil returns an error.
func TestAIGeneratedMetadata_ValidateNil(t *testing.T) {
	var m *nlg.AIGeneratedMetadata
	if err := m.Validate(); err == nil {
		t.Fatal("expected error for nil metadata, got nil")
	}
}

// TestAIGeneratedMetadata_ValidateNotMarked verifies is_ai_generated=false returns error.
func TestAIGeneratedMetadata_ValidateNotMarked(t *testing.T) {
	m := &nlg.AIGeneratedMetadata{
		IsAIGenerated: false, // wrong
		Model:         "llama-3.2-3b-instruct",
		GeneratedAt:   time.Now().UTC(),
		Language:      "de",
	}
	if err := m.Validate(); err == nil {
		t.Fatal("expected error when is_ai_generated=false, got nil")
	}
}

// TestAIGeneratedMetadata_ValidateMissingModel verifies missing model returns error.
func TestAIGeneratedMetadata_ValidateMissingModel(t *testing.T) {
	m := &nlg.AIGeneratedMetadata{
		IsAIGenerated: true,
		Model:         "", // missing
		GeneratedAt:   time.Now().UTC(),
		Language:      "de",
	}
	if err := m.Validate(); err == nil {
		t.Fatal("expected error for missing model, got nil")
	}
}

// TestAIGeneratedMetadata_ValidateMissingTimestamp verifies zero GeneratedAt returns error.
func TestAIGeneratedMetadata_ValidateMissingTimestamp(t *testing.T) {
	m := &nlg.AIGeneratedMetadata{
		IsAIGenerated: true,
		Model:         "llama-3.2-3b-instruct",
		GeneratedAt:   time.Time{}, // zero
		Language:      "de",
	}
	if err := m.Validate(); err == nil {
		t.Fatal("expected error for zero GeneratedAt, got nil")
	}
}

// TestAIGeneratedMetadata_ValidateMissingLanguage verifies missing language returns error.
func TestAIGeneratedMetadata_ValidateMissingLanguage(t *testing.T) {
	m := &nlg.AIGeneratedMetadata{
		IsAIGenerated: true,
		Model:         "llama-3.2-3b-instruct",
		GeneratedAt:   time.Now().UTC(),
		Language:      "", // missing
	}
	if err := m.Validate(); err == nil {
		t.Fatal("expected error for missing language, got nil")
	}
}

// TestPromptHash is deterministic for same input.
func TestPromptHash(t *testing.T) {
	h1 := nlg.PromptHash("BMW 320d 2020 DE")
	h2 := nlg.PromptHash("BMW 320d 2020 DE")
	h3 := nlg.PromptHash("different input")
	if h1 != h2 {
		t.Error("PromptHash must be deterministic")
	}
	if h1 == h3 {
		t.Error("PromptHash must differ for different inputs")
	}
	if len(h1) != 64 {
		t.Errorf("PromptHash expected 64 hex chars, got %d", len(h1))
	}
}
