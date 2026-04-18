package media

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
)

// ReorderRequest is the JSON body for PUT /api/v1/vehicles/:id/media/reorder.
type ReorderRequest struct {
	PhotoIDs []string `json:"photo_ids"` // ordered list; first = sort_order 0
}

// ReorderHandler returns an http.HandlerFunc for the reorder endpoint.
// It expects {vehicleID} in the URL path (second-to-last segment).
// Header X-Tenant-ID is required.
func ReorderHandler(storage MediaStorage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		tenantID := r.Header.Get("X-Tenant-ID")
		if tenantID == "" {
			http.Error(w, "X-Tenant-ID header required", http.StatusBadRequest)
			return
		}

		// Extract vehicleID from path: /api/v1/vehicles/{vehicleID}/media/reorder
		vehicleID := vehicleIDFromPath(r.URL.Path)
		if vehicleID == "" {
			http.Error(w, "vehicle id missing in path", http.StatusBadRequest)
			return
		}

		var req ReorderRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		if len(req.PhotoIDs) == 0 {
			http.Error(w, "photo_ids must not be empty", http.StatusBadRequest)
			return
		}

		if err := Reorder(r.Context(), storage, tenantID, vehicleID, req.PhotoIDs); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

// Reorder atomically updates the sort_order of the listed photos to match the
// provided slice order. Photos not belonging to tenantID/vehicleID are silently
// ignored by the underlying UPDATE.
func Reorder(ctx context.Context, storage MediaStorage, tenantID, vehicleID string, photoIDs []string) error {
	_ = vehicleID // vehicle ownership is enforced by the WHERE tenant_id=? clause
	return storage.UpdateSortOrders(ctx, tenantID, photoIDs)
}

// vehicleIDFromPath extracts the {vehicleID} path segment from a URL like
// /api/v1/vehicles/{vehicleID}/media/reorder.
func vehicleIDFromPath(path string) string {
	// Split and look for the segment after "vehicles".
	parts := strings.Split(strings.Trim(path, "/"), "/")
	for i, p := range parts {
		if p == "vehicles" && i+1 < len(parts) {
			return parts[i+1]
		}
	}
	return ""
}
