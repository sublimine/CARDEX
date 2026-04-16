// Package run exposes a minimal public API over the extraction module's
// internal packages, intended exclusively for e2e integration tests.
//
// Production code uses the extraction service binary. This package exists to
// allow an external test module to drive the E01/E02 extraction strategies
// and persist results without importing internal packages directly.
package run

import (
	"context"
	"net/http"

	"cardex.eu/extraction/internal/extractor/e01_jsonld"
	"cardex.eu/extraction/internal/pipeline"
	"cardex.eu/extraction/internal/storage"
)

// Type aliases re-export internal types so that the e2e module can use them
// without importing the internal packages directly.

// Dealer is the input to the extraction pipeline.
type Dealer = pipeline.Dealer

// VehicleRaw is a vehicle record in raw post-extraction format.
type VehicleRaw = pipeline.VehicleRaw

// ExtractionResult encapsulates the outcome of a single strategy run.
type ExtractionResult = pipeline.ExtractionResult

// ExtractE01 runs the E01 JSON-LD extraction strategy against dealer.
// httpClient is injected so tests can route requests to a local fixture server.
// rateLimitMs = 0 means the strategy's minimum floor (50 ms) is used.
func ExtractE01(ctx context.Context, dealer *Dealer, httpClient *http.Client) (*ExtractionResult, error) {
	s := e01_jsonld.NewWithClient(httpClient, 0)
	return s.Extract(ctx, *dealer)
}

// PersistVehicles opens the SQLite storage at dbPath and upserts the vehicles
// into vehicle_record. The discovery schema (dealer_entity, vehicle_record)
// must already be present; call discovery/run.InitDB first.
// Returns the number of newly inserted rows.
func PersistVehicles(ctx context.Context, dbPath string, dealerID string, vehicles []*VehicleRaw) (int, error) {
	store, err := storage.New(dbPath)
	if err != nil {
		return 0, err
	}
	defer store.Close()
	return store.PersistVehicles(ctx, dealerID, vehicles)
}
