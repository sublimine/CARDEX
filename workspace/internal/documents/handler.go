package documents

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path"
	"strings"
)

const maxRequestBodyBytes = 512 * 1024 // 512 KB — enough for any document request JSON

// Handler returns a mux wired to all document endpoints.
//
//	POST /api/v1/documents/contract
//	POST /api/v1/documents/invoice
//	POST /api/v1/documents/vehicle-sheet
//	POST /api/v1/documents/transport
//	GET  /api/v1/documents/{id}/download
func Handler(svc *Service) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/documents/contract", svc.handleContract)
	mux.HandleFunc("/api/v1/documents/invoice", svc.handleInvoice)
	mux.HandleFunc("/api/v1/documents/vehicle-sheet", svc.handleVehicleSheet)
	mux.HandleFunc("/api/v1/documents/transport", svc.handleTransport)
	mux.HandleFunc("/api/v1/documents/", svc.handleDownload) // /{id}/download
	return mux
}

func (s *Service) handleContract(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var req ContractRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}
	if req.VehicleID == "" || req.Country == "" {
		writeError(w, http.StatusBadRequest, "vehicle_id and country are required")
		return
	}
	result, err := s.GenerateContract(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (s *Service) handleInvoice(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var req InvoiceRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}
	if req.DealID == "" {
		writeError(w, http.StatusBadRequest, "deal_id is required")
		return
	}
	result, err := s.GenerateInvoice(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (s *Service) handleVehicleSheet(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var req VehicleSheetRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}
	if req.VehicleID == "" {
		writeError(w, http.StatusBadRequest, "vehicle_id is required")
		return
	}
	result, err := s.GenerateVehicleSheet(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (s *Service) handleTransport(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var req TransportRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}
	if req.VehicleID == "" {
		writeError(w, http.StatusBadRequest, "vehicle_id is required")
		return
	}
	result, err := s.GenerateTransportDoc(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

// handleDownload serves the PDF file for GET /api/v1/documents/{id}/download.
func (s *Service) handleDownload(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract {id} from /api/v1/documents/{id}/download
	trimmed := strings.TrimPrefix(r.URL.Path, "/api/v1/documents/")
	id := path.Dir(trimmed)
	if id == "." || id == "" {
		writeError(w, http.StatusBadRequest, "missing document id")
		return
	}

	doc, err := s.GetDocumentFile(r.Context(), id)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeError(w, http.StatusNotFound, fmt.Sprintf("document %q not found", id))
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	f, err := os.Open(doc.FilePath)
	if err != nil {
		writeError(w, http.StatusNotFound, "file not found on disk")
		return
	}
	defer f.Close()

	fileName := path.Base(doc.FilePath)
	w.Header().Set("Content-Type", "application/pdf")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, fileName))
	http.ServeContent(w, r, fileName, doc.CreatedAt, f)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
