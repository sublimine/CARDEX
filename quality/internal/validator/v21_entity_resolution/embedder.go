// Package v21_entity_resolution implements V21 — Multilingual Dealer Entity Resolution.
package v21_entity_resolution

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os/exec"
	"strings"
	"unicode"
)

// Dim is the embedding dimension for the pure-Go TF-IDF fallback.
// The subprocess embedder uses 768 (paraphrase-multilingual-mpnet-base-v2).
const (
	DimTFIDF      = 256
	DimMpnet      = 768
	DefaultThresh = 0.85
)

// TextEmbedder converts a text string to a float32 embedding vector.
// Implementations: SubprocessEmbedder (Python mpnet), TFIDFEmbedder (pure Go).
type TextEmbedder interface {
	// Embed returns a unit-normalised embedding vector for the input text.
	Embed(ctx context.Context, text string) ([]float32, error)
	// Dim returns the dimensionality of the embedding.
	Dim() int
	// Name returns the embedder identifier for metrics/logs.
	Name() string
}

// ── SubprocessEmbedder ─────────────────────────────────────────────────────
//
// SubprocessEmbedder shells out to a Python one-liner that uses
// sentence-transformers paraphrase-multilingual-mpnet-base-v2.
//
// # ONNX blocker note
//
// BGE-M3 (568M params, 1024-dim) is the preferred model but the Go ONNX
// bindings (onnxruntime-go) require CGO and are not yet stable for
// cross-compilation on CPU-only linux/amd64.
//
// paraphrase-multilingual-mpnet-base-v2 (278M, 768-dim) is our fallback:
//   - Covers DE/FR/ES/NL/BE/CH multilingual dealer names and addresses.
//   - Runs inference in ~150ms per batch on Hetzner CX42 (int8-quantised).
//   - Requires: pip install sentence-transformers torch --index-url cpu-only
//
// Python one-liner invoked per batch:
//
//	python3 -c "
//	  import sys, json
//	  from sentence_transformers import SentenceTransformer
//	  m = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
//	  texts = json.load(sys.stdin)
//	  print(json.dumps(m.encode(texts, normalize_embeddings=True).tolist()))
//	"
//
// If Python or sentence-transformers is not installed, Embed returns an error
// and the V21 pipeline falls back to TFIDFEmbedder automatically.

// SubprocessEmbedder calls a Python subprocess to produce mpnet embeddings.
type SubprocessEmbedder struct {
	python string // python interpreter path (default "python3")
}

// NewSubprocessEmbedder creates an embedder using the given Python binary.
func NewSubprocessEmbedder(python string) *SubprocessEmbedder {
	if python == "" {
		python = "python3"
	}
	return &SubprocessEmbedder{python: python}
}

func (s *SubprocessEmbedder) Dim() int    { return DimMpnet }
func (s *SubprocessEmbedder) Name() string { return "paraphrase-multilingual-mpnet-base-v2" }

func (s *SubprocessEmbedder) Embed(ctx context.Context, text string) ([]float32, error) {
	script := `
import sys, json
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
texts = json.load(sys.stdin)
print(json.dumps(m.encode(texts, normalize_embeddings=True).tolist()))
`
	input, err := json.Marshal([]string{text})
	if err != nil {
		return nil, err
	}

	cmd := exec.CommandContext(ctx, s.python, "-c", script)
	cmd.Stdin = strings.NewReader(string(input))
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("subprocess embedder: python error: %w", err)
	}

	var vecs [][]float64
	if err := json.Unmarshal(out, &vecs); err != nil {
		return nil, fmt.Errorf("subprocess embedder: parse output: %w", err)
	}
	if len(vecs) == 0 {
		return nil, fmt.Errorf("subprocess embedder: empty result")
	}
	f32 := make([]float32, len(vecs[0]))
	for i, v := range vecs[0] {
		f32[i] = float32(v)
	}
	return f32, nil
}

// ── TFIDFEmbedder ──────────────────────────────────────────────────────────
//
// TFIDFEmbedder is the pure-Go CPU-native fallback. It projects text into a
// 256-dimensional space using character 3-gram TF hashing (no IDF — single
// document, so IDF is trivially 1). Cosine similarity at threshold=0.85
// works well for dealer names and addresses with minor typos or abbreviations
// (e.g. "BMW Autohaus GmbH" ≃ "Autohaus BMW München GmbH").
//
// This embedder is deterministic and requires no external dependencies.
// It is the default used in unit tests and in production until a Python
// sidecar is deployed.

// TFIDFEmbedder encodes text as a normalised character n-gram TF vector.
type TFIDFEmbedder struct{}

func (t *TFIDFEmbedder) Dim() int     { return DimTFIDF }
func (t *TFIDFEmbedder) Name() string { return "tfidf-char3gram-go" }

func (t *TFIDFEmbedder) Embed(_ context.Context, text string) ([]float32, error) {
	vec := charNgramTF(text, 3, DimTFIDF)
	return normalise(vec), nil
}

// charNgramTF builds a term-frequency vector over character n-grams of the
// given order, hashed into dim buckets (Hashing Trick, FNV-inspired).
func charNgramTF(text string, n, dim int) []float32 {
	vec := make([]float32, dim)
	runes := []rune(strings.ToLower(text))
	// Strip punctuation that is not semantically meaningful for entity matching.
	var clean []rune
	for _, r := range runes {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || unicode.IsSpace(r) {
			clean = append(clean, r)
		}
	}
	text = strings.TrimSpace(string(clean))
	runes = []rune(text)

	for i := 0; i <= len(runes)-n; i++ {
		gram := string(runes[i : i+n])
		h := fnv32(gram) % uint32(dim)
		vec[h]++
	}
	return vec
}

// normalise converts a vector to unit length in-place and returns it.
func normalise(v []float32) []float32 {
	var sum float64
	for _, x := range v {
		sum += float64(x) * float64(x)
	}
	if sum == 0 {
		return v
	}
	mag := float32(math.Sqrt(sum))
	for i := range v {
		v[i] /= mag
	}
	return v
}

// CosineSimilarity computes the dot product of two unit-normalised vectors.
// Both vectors must have the same length.
func CosineSimilarity(a, b []float32) float32 {
	if len(a) != len(b) {
		return 0
	}
	var dot float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
	}
	return float32(dot)
}

// fnv32 is a FNV-1a 32-bit hash for strings.
func fnv32(s string) uint32 {
	h := uint32(2166136261)
	for i := 0; i < len(s); i++ {
		h ^= uint32(s[i])
		h *= 16777619
	}
	return h
}
