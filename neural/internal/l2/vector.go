package l2

import (
	"context"
	"encoding/json"
	"fmt"
	"math"

	"github.com/redis/go-redis/v9"
)

const (
	indexName           = "idx:vehicle_embeddings"
	keyPrefix           = "emb:"
	defaultDimensions   = 768
	similarityThreshold = 0.92
	confidenceThreshold = 0.95
)

type Result struct {
	TaxStatus  string  `json:"tax_status"`
	Confidence float64 `json:"confidence"`
	Similarity float64 `json:"similarity"`
	SourceULID string  `json:"source_ulid"`
}

type Embedder interface {
	Embed(ctx context.Context, text string) ([]float32, error)
}

type Store struct {
	rdb        *redis.Client
	embedder   Embedder
	dimensions int
}

func NewStore(rdb *redis.Client, embedder Embedder) *Store {
	return &Store{rdb: rdb, embedder: embedder, dimensions: defaultDimensions}
}

func (s *Store) EnsureIndex(ctx context.Context) error {
	args := []interface{}{
		"FT.CREATE", indexName, "ON", "HASH", "PREFIX", "1", keyPrefix,
		"SCHEMA", "tax_status", "TAG", "confidence", "NUMERIC",
		"embedding", "VECTOR", "HNSW", "6",
		"TYPE", "FLOAT32", "DIM", s.dimensions, "DISTANCE_METRIC", "COSINE",
	}
	err := s.rdb.Do(ctx, args...).Err()
	if err != nil && err.Error() == "Index already exists" {
		return nil
	}
	return err
}

func (s *Store) Index(ctx context.Context, vehicleULID string, description string, taxStatus string, confidence float64) error {
	embedding, err := s.embedder.Embed(ctx, description)
	if err != nil {
		return fmt.Errorf("l2: embed: %w", err)
	}
	key := keyPrefix + vehicleULID
	return s.rdb.HSet(ctx, key, "tax_status", taxStatus, "confidence", confidence, "embedding", float32SliceToBytes(embedding)).Err()
}

func (s *Store) Search(ctx context.Context, description string) (Result, bool) {
	embedding, err := s.embedder.Embed(ctx, description)
	if err != nil {
		return Result{}, false
	}
	query := fmt.Sprintf("(@confidence:[%.2f +inf])=>[KNN 1 @embedding $vec AS similarity]", confidenceThreshold)
	args := []interface{}{
		"FT.SEARCH", indexName, query,
		"PARAMS", "2", "vec", float32SliceToBytes(embedding),
		"SORTBY", "similarity", "ASC",
		"RETURN", "3", "tax_status", "confidence", "similarity",
		"LIMIT", "0", "1", "DIALECT", "2",
	}
	res, err := s.rdb.Do(ctx, args...).Result()
	if err != nil {
		return Result{}, false
	}
	return parseSearchResult(res)
}

func (s *Store) Size(ctx context.Context) (int64, error) {
	res, err := s.rdb.Do(ctx, "FT.INFO", indexName).Result()
	if err != nil {
		return 0, err
	}
	return parseInfoNumDocs(res), nil
}

func parseSearchResult(raw interface{}) (Result, bool) {
	arr, ok := raw.([]interface{})
	if !ok || len(arr) < 3 {
		return Result{}, false
	}
	total, ok := arr[0].(int64)
	if !ok || total == 0 {
		return Result{}, false
	}
	docKey, _ := arr[1].(string)
	fields, ok := arr[2].([]interface{})
	if !ok {
		return Result{}, false
	}
	var r Result
	if len(docKey) > 4 {
		r.SourceULID = docKey[4:]
	}
	for i := 0; i+1 < len(fields); i += 2 {
		key, _ := fields[i].(string)
		val, _ := fields[i+1].(string)
		switch key {
		case "tax_status":
			r.TaxStatus = val
		case "confidence":
			fmt.Sscanf(val, "%f", &r.Confidence)
		case "similarity":
			var dist float64
			fmt.Sscanf(val, "%f", &dist)
			r.Similarity = 1.0 - dist
		}
	}
	if r.Similarity < similarityThreshold || r.Confidence < confidenceThreshold {
		return Result{}, false
	}
	return r, true
}

func parseInfoNumDocs(raw interface{}) int64 {
	arr, ok := raw.([]interface{})
	if !ok {
		return 0
	}
	for i := 0; i+1 < len(arr); i++ {
		key, _ := arr[i].(string)
		if key == "num_docs" {
			val, _ := arr[i+1].(string)
			var n int64
			fmt.Sscanf(val, "%d", &n)
			return n
		}
	}
	return 0
}

func float32SliceToBytes(v []float32) []byte {
	buf := make([]byte, len(v)*4)
	for i, f := range v {
		bits := math.Float32bits(f)
		buf[i*4] = byte(bits)
		buf[i*4+1] = byte(bits >> 8)
		buf[i*4+2] = byte(bits >> 16)
		buf[i*4+3] = byte(bits >> 24)
	}
	return buf
}

func bytesToFloat32Slice(b []byte) []float32 {
	if len(b)%4 != 0 {
		return nil
	}
	v := make([]float32, len(b)/4)
	for i := range v {
		bits := uint32(b[i*4]) | uint32(b[i*4+1])<<8 | uint32(b[i*4+2])<<16 | uint32(b[i*4+3])<<24
		v[i] = math.Float32frombits(bits)
	}
	return v
}

func CosineSimilarity(a, b []float32) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 0
	}
	var dot, normA, normB float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		normA += float64(a[i]) * float64(a[i])
		normB += float64(b[i]) * float64(b[i])
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

type MockEmbedder struct {
	Mappings map[string][]float32
}

func (m *MockEmbedder) Embed(_ context.Context, text string) ([]float32, error) {
	if v, ok := m.Mappings[text]; ok {
		return v, nil
	}
	emb := make([]float32, defaultDimensions)
	for i, c := range text {
		emb[i%defaultDimensions] += float32(c) / 1000.0
	}
	var norm float64
	for _, v := range emb {
		norm += float64(v) * float64(v)
	}
	if norm > 0 {
		sn := float32(math.Sqrt(norm))
		for i := range emb {
			emb[i] /= sn
		}
	}
	return emb, nil
}

type NomicEmbedder struct{ BaseURL string }

func (n *NomicEmbedder) Embed(ctx context.Context, text string) ([]float32, error) {
	return nil, fmt.Errorf("l2: NomicEmbedder requires llama-server at %s", n.BaseURL)
}

var _ Embedder = (*MockEmbedder)(nil)
var _ Embedder = (*NomicEmbedder)(nil)
var _ json.Marshaler = nil
