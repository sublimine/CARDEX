// Package h3 provides H3 geospatial indexing for the Phase 4 pipeline.
// Resolution 4: ~1,700 km². Resolution 7: ~5 km² for proximity matching.
package h3

import (
	"fmt"

	"github.com/uber/h3-go/v4"
)

// Indexer converts GPS coordinates to H3 indexes. No external dependencies.
type Indexer struct{}

// Compute converts lat/lng to H3 indexes at resolution 4 and 7.
// Returns (res4, res7, nil) or ("", "", error) if lat/lng are both zero (null island).
func (i *Indexer) Compute(lat, lng float64) (res4 string, res7 string, err error) {
	if lat == 0 && lng == 0 {
		return "", "", fmt.Errorf("h3: null island coordinates rejected")
	}
	latLng := h3.NewLatLng(lat, lng)
	cell4, err := h3.LatLngToCell(latLng, 4)
	if err != nil {
		return "", "", fmt.Errorf("h3: resolution 4: %w", err)
	}
	cell7, err := h3.LatLngToCell(latLng, 7)
	if err != nil {
		return "", "", fmt.Errorf("h3: resolution 7: %w", err)
	}
	return cell4.String(), cell7.String(), nil
}
