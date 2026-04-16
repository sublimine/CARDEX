// Package nlg provides types and helpers for AI-generated content compliance
// under EU AI Act Art. 50 (Reg. 2024/1689), which requires machine-readable
// marking of AI-generated text outputs from 2 August 2026.
//
// # Applicability
//
// Art. 50(2) applies to providers of AI systems that generate synthetic text.
// CARDEX operates a local LLM (Llama 3 / Qwen2.5) to generate vehicle
// descriptions. As the operator of that model, CARDEX is the "provider" for
// the purpose of Art. 50(2) and must include machine-readable metadata in
// every AI-generated text output.
//
// # Usage
//
// Populate an AIGeneratedMetadata value at generation time and attach it to
// the Vehicle record's AIGeneratedMeta field before the vehicle enters the
// quality pipeline.
//
//	meta := nlg.AIGeneratedMetadata{
//	    IsAIGenerated: true,
//	    Model:         "llama-3.2-3b-instruct",
//	    ModelVersion:  "Q4_K_M",
//	    GeneratedAt:   time.Now().UTC(),
//	    PromptHash:    nlg.PromptHash(promptText),
//	    Language:      "de",
//	}
//	vehicle.AIGeneratedMeta = &meta
package nlg

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"time"
)

// AIGeneratedMetadata carries the AI Act Art. 50(2) disclosure fields that
// must be present in every AI-generated text output served by CARDEX.
//
// The struct is designed for direct JSON serialisation as the "ai_generated"
// field in any API response that includes an NLG-produced description.
//
// All fields are exported and json-tagged for serialisation compatibility with
// both the internal quality pipeline and the external API layer.
type AIGeneratedMetadata struct {
	// IsAIGenerated is always true when this struct is present. It serves as
	// the primary machine-readable marker required by Art. 50(2).
	IsAIGenerated bool `json:"is_ai_generated"`

	// Model is the name of the model used to generate the text.
	// Example: "llama-3.2-3b-instruct", "qwen2.5-7b-instruct".
	Model string `json:"model"`

	// ModelVersion captures the quantisation or fine-tune tag.
	// Example: "Q4_K_M", "GGUF-fp16".
	ModelVersion string `json:"model_version"`

	// GeneratedAt is the UTC timestamp at which generation occurred.
	GeneratedAt time.Time `json:"generated_at"`

	// PromptHash is the SHA-256 hex digest of the prompt template + inputs
	// used to generate the description. Enables audit reproducibility.
	PromptHash string `json:"prompt_hash"`

	// Language is the BCP-47 language tag of the generated text.
	// Example: "de", "fr", "es", "nl".
	Language string `json:"language"`
}

// PromptHash returns the hex-encoded SHA-256 digest of the given prompt
// string. Use this to populate AIGeneratedMetadata.PromptHash.
func PromptHash(prompt string) string {
	sum := sha256.Sum256([]byte(prompt))
	return hex.EncodeToString(sum[:])
}

// MarshalJSON implements json.Marshaler. It is a pass-through to the default
// struct marshaller but ensures zero-value structs are not silently serialised
// with is_ai_generated=false — callers must use a non-nil pointer.
func (m AIGeneratedMetadata) MarshalJSON() ([]byte, error) {
	type alias AIGeneratedMetadata
	return json.Marshal(alias(m))
}

// Validate returns a non-nil error if any required field is missing or invalid.
// A valid AIGeneratedMetadata must have IsAIGenerated=true, a non-empty Model,
// a non-zero GeneratedAt, and a non-empty Language.
func (m *AIGeneratedMetadata) Validate() error {
	if m == nil {
		return errNilMetadata
	}
	if !m.IsAIGenerated {
		return errNotMarked
	}
	if m.Model == "" {
		return errMissingModel
	}
	if m.GeneratedAt.IsZero() {
		return errMissingTimestamp
	}
	if m.Language == "" {
		return errMissingLanguage
	}
	return nil
}

// sentinel errors — unexported, compared by identity in tests.
var (
	errNilMetadata    = aiActError("ai_generated metadata is nil")
	errNotMarked      = aiActError("is_ai_generated must be true")
	errMissingModel   = aiActError("model field is required")
	errMissingTimestamp = aiActError("generated_at field is required")
	errMissingLanguage  = aiActError("language field is required")
)

type aiActError string

func (e aiActError) Error() string { return string(e) }
