package v21_entity_resolution

import (
	"context"
	"database/sql"
	"encoding/binary"
	"fmt"
	"math"
)

// IndexEntry is a single record in the embedding index.
type IndexEntry struct {
	EntityID  string
	Text      string
	Embedding []float32
}

// EmbeddingIndex stores and searches entity embeddings.
// SQLite-backed for persistence; linear scan for MVP scale (< 50k dealers).
//
// Schema created on first use:
//
//	CREATE TABLE IF NOT EXISTS entity_embeddings (
//	    entity_id   TEXT NOT NULL,
//	    entity_type TEXT NOT NULL DEFAULT 'dealer',
//	    text        TEXT NOT NULL,
//	    dim         INTEGER NOT NULL,
//	    embedding   BLOB NOT NULL,
//	    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
//	    PRIMARY KEY (entity_id, entity_type)
//	);
type EmbeddingIndex struct {
	db  *sql.DB
	dim int
}

// NewEmbeddingIndex opens (or creates) the embedding index in the given DB.
func NewEmbeddingIndex(db *sql.DB, dim int) (*EmbeddingIndex, error) {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS entity_embeddings (
		    entity_id   TEXT NOT NULL,
		    entity_type TEXT NOT NULL DEFAULT 'dealer',
		    text        TEXT NOT NULL,
		    dim         INTEGER NOT NULL,
		    embedding   BLOB NOT NULL,
		    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
		    PRIMARY KEY (entity_id, entity_type)
		)`)
	if err != nil {
		return nil, fmt.Errorf("entity_embeddings schema: %w", err)
	}
	return &EmbeddingIndex{db: db, dim: dim}, nil
}

// Upsert inserts or replaces the embedding for entity_id.
func (idx *EmbeddingIndex) Upsert(ctx context.Context, entry IndexEntry) error {
	blob := float32ToBlob(entry.Embedding)
	_, err := idx.db.ExecContext(ctx, `
		INSERT OR REPLACE INTO entity_embeddings(entity_id, text, dim, embedding)
		VALUES (?, ?, ?, ?)`,
		entry.EntityID, entry.Text, len(entry.Embedding), blob,
	)
	return err
}

// SearchResult is a candidate match from the index.
type SearchResult struct {
	EntityID   string
	Text       string
	Similarity float32
}

// Search returns all entries with cosine similarity ≥ minSim to the query
// vector, sorted descending. Excludes excludeID (the query entity itself).
func (idx *EmbeddingIndex) Search(ctx context.Context, query []float32, minSim float32, excludeID string) ([]SearchResult, error) {
	rows, err := idx.db.QueryContext(ctx, `
		SELECT entity_id, text, embedding FROM entity_embeddings
		WHERE entity_id != ?`, excludeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []SearchResult
	for rows.Next() {
		var eid, text string
		var blob []byte
		if err := rows.Scan(&eid, &text, &blob); err != nil {
			return nil, err
		}
		vec := blobToFloat32(blob)
		if len(vec) != len(query) {
			continue // dimension mismatch (embedder changed)
		}
		sim := CosineSimilarity(query, vec)
		if sim >= minSim {
			results = append(results, SearchResult{EntityID: eid, Text: text, Similarity: sim})
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	// Sort descending by similarity.
	sortSearchResults(results)
	return results, nil
}

func sortSearchResults(r []SearchResult) {
	for i := 1; i < len(r); i++ {
		for j := i; j > 0 && r[j].Similarity > r[j-1].Similarity; j-- {
			r[j], r[j-1] = r[j-1], r[j]
		}
	}
}

// float32ToBlob encodes a float32 slice as little-endian bytes.
func float32ToBlob(v []float32) []byte {
	b := make([]byte, len(v)*4)
	for i, f := range v {
		binary.LittleEndian.PutUint32(b[i*4:], math.Float32bits(f))
	}
	return b
}

// blobToFloat32 decodes little-endian bytes back to float32 slice.
func blobToFloat32(b []byte) []float32 {
	if len(b)%4 != 0 {
		return nil
	}
	v := make([]float32, len(b)/4)
	for i := range v {
		v[i] = math.Float32frombits(binary.LittleEndian.Uint32(b[i*4:]))
	}
	return v
}
