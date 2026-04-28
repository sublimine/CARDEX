package tax

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// Server handles HTTP requests for the VAT calculation API.
type Server struct {
	vies   *VIESClient
	logger *slog.Logger
}

// NewServer creates a Server with the given VIES client and logger.
func NewServer(vies *VIESClient, logger *slog.Logger) *Server {
	return &Server{vies: vies, logger: logger}
}

// Handler returns an http.Handler for the tax API.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /tax/calculate", s.handleCalculate)
	mux.HandleFunc("GET /health", s.handleHealth)
	return mux
}

func (s *Server) handleCalculate(w http.ResponseWriter, r *http.Request) {
	var req CalculationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, "invalid JSON body", http.StatusBadRequest)
		return
	}

	if !IsEUCountry(req.FromCountry) && req.FromCountry != "CH" {
		jsonError(w, fmt.Sprintf("unsupported from_country: %s", req.FromCountry), http.StatusBadRequest)
		return
	}
	if !IsEUCountry(req.ToCountry) && req.ToCountry != "CH" {
		jsonError(w, fmt.Sprintf("unsupported to_country: %s", req.ToCountry), http.StatusBadRequest)
		return
	}
	if req.FromCountry == req.ToCountry {
		jsonError(w, "from_country and to_country must differ", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	viesStatus := s.vies.ValidateBoth(ctx, req.SellerVATID, req.BuyerVATID)

	resp := Calculate(req, viesStatus)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"service": "cardex-tax-engine",
		"port":    "8504",
	})
}

func jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
