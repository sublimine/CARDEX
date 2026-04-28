package finance

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const maxBodyBytes = 64 * 1024 // 64 KB — sufficient for any transaction JSON

// Handler returns an http.Handler for all finance endpoints.
//
//	POST   /api/v1/vehicles/{id}/transactions
//	GET    /api/v1/vehicles/{id}/transactions
//	GET    /api/v1/vehicles/{id}/pnl
//	GET    /api/v1/fleet/pnl/monthly?year=&month=
//	GET    /api/v1/fleet/pnl?from=&to=
//	GET    /api/v1/fleet/alerts
//	PUT    /api/v1/transactions/{id}
//	DELETE /api/v1/transactions/{id}
func Handler(store *Store, calc *Calculator, alertSvc *AlertService) http.Handler {
	h := &financeHandler{store: store, calc: calc, alertSvc: alertSvc}
	mux := http.NewServeMux()

	mux.HandleFunc("POST /api/v1/vehicles/{id}/transactions", h.createTx)
	mux.HandleFunc("GET /api/v1/vehicles/{id}/transactions", h.listTx)
	mux.HandleFunc("GET /api/v1/vehicles/{id}/pnl", h.vehiclePnL)
	// Register more-specific monthly route first; Go 1.22 picks longest match.
	mux.HandleFunc("GET /api/v1/fleet/pnl/monthly", h.monthlyPnL)
	mux.HandleFunc("GET /api/v1/fleet/pnl", h.fleetPnL)
	mux.HandleFunc("GET /api/v1/fleet/alerts", h.fleetAlerts)
	mux.HandleFunc("PUT /api/v1/transactions/{id}", h.updateTx)
	mux.HandleFunc("DELETE /api/v1/transactions/{id}", h.deleteTx)

	return mux
}

type financeHandler struct {
	store    *Store
	calc     *Calculator
	alertSvc *AlertService
}

func (h *financeHandler) createTx(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	if tenant == "" {
		jsonErr(w, http.StatusBadRequest, errMissing("X-Tenant-ID"))
		return
	}
	vehicleID := r.PathValue("id")

	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	var req CreateTransactionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonErr(w, http.StatusBadRequest, err)
		return
	}
	tx, err := h.store.Create(tenant, vehicleID, req)
	if err != nil {
		jsonErr(w, http.StatusBadRequest, err)
		return
	}
	metricTransactionsTotal.Add(1)
	jsonOK(w, http.StatusCreated, tx)
}

func (h *financeHandler) listTx(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	vehicleID := r.PathValue("id")
	txs, err := h.store.ListByVehicle(tenant, vehicleID)
	if err != nil {
		jsonErr(w, http.StatusInternalServerError, err)
		return
	}
	if txs == nil {
		txs = []Transaction{}
	}
	jsonOK(w, http.StatusOK, txs)
}

func (h *financeHandler) vehiclePnL(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	vehicleID := r.PathValue("id")
	pnl, err := h.calc.CalculateVehiclePnL(tenant, vehicleID)
	if err != nil {
		jsonErr(w, http.StatusInternalServerError, err)
		return
	}
	jsonOK(w, http.StatusOK, pnl)
}

func (h *financeHandler) fleetPnL(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	from := r.URL.Query().Get("from")
	to := r.URL.Query().Get("to")
	if from == "" {
		from = time.Now().AddDate(0, -3, 0).Format("2006-01-02")
	}
	if to == "" {
		to = time.Now().Format("2006-01-02")
	}
	pnl, err := h.calc.CalculateFleetPnL(tenant, from, to)
	if err != nil {
		jsonErr(w, http.StatusInternalServerError, err)
		return
	}
	jsonOK(w, http.StatusOK, pnl)
}

func (h *financeHandler) monthlyPnL(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	now := time.Now()
	year, _ := strconv.Atoi(r.URL.Query().Get("year"))
	month, _ := strconv.Atoi(r.URL.Query().Get("month"))
	if year == 0 {
		year = now.Year()
	}
	if month < 1 || month > 12 {
		month = int(now.Month())
	}
	pnl, err := h.calc.CalculateMonthlyPnL(tenant, year, month)
	if err != nil {
		jsonErr(w, http.StatusInternalServerError, err)
		return
	}
	jsonOK(w, http.StatusOK, pnl)
}

func (h *financeHandler) fleetAlerts(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	alerts, err := h.alertSvc.GetAlerts(tenant)
	if err != nil {
		jsonErr(w, http.StatusInternalServerError, err)
		return
	}
	if alerts == nil {
		alerts = []Alert{}
	}
	jsonOK(w, http.StatusOK, alerts)
}

func (h *financeHandler) updateTx(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	if tenant == "" {
		jsonErr(w, http.StatusBadRequest, errMissing("X-Tenant-ID"))
		return
	}
	id := r.PathValue("id")
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	var req CreateTransactionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonErr(w, http.StatusBadRequest, err)
		return
	}
	tx, err := h.store.Update(tenant, id, req)
	if err != nil {
		jsonErr(w, http.StatusNotFound, err)
		return
	}
	jsonOK(w, http.StatusOK, tx)
}

func (h *financeHandler) deleteTx(w http.ResponseWriter, r *http.Request) {
	tenant := tenantFrom(r)
	id := r.PathValue("id")
	if err := h.store.Delete(tenant, id); err != nil {
		jsonErr(w, http.StatusNotFound, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── helpers ───────────────────────────────────────────────────────────────────

func tenantFrom(r *http.Request) string {
	if t := r.Header.Get("X-Tenant-ID"); t != "" {
		return t
	}
	for i, p := range strings.Split(r.URL.Path, "/") {
		if p == "tenants" && i+1 < len(strings.Split(r.URL.Path, "/")) {
			return strings.Split(r.URL.Path, "/")[i+1]
		}
	}
	return "" // callers must reject empty tenant
}

type errMissing string

func (e errMissing) Error() string { return string(e) + " header is required" }

func jsonOK(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func jsonErr(w http.ResponseWriter, status int, err error) {
	jsonOK(w, status, map[string]string{"error": err.Error()})
}
