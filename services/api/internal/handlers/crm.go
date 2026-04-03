package handlers

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"
)

// ── CRM Dashboard ─────────────────────────────────────────────────────────────

type crmInventoryStatus struct {
	Total    int            `json:"total"`
	ByStatus map[string]int `json:"by_status"`
}

type crmPipelineSummary struct {
	OpenDeals        int     `json:"open_deals"`
	PipelineValueEUR float64 `json:"pipeline_value_eur"`
}

type crmMTD struct {
	UnitsSold    int     `json:"units_sold"`
	RevenueEUR   float64 `json:"revenue_eur"`
	AvgMarginPct float64 `json:"avg_margin_pct"`
	AvgDOM       float64 `json:"avg_dom"`
}

type crmTopContact struct {
	ContactULID      string  `json:"contact_ulid"`
	FullName         string  `json:"full_name"`
	LifetimeValueEUR float64 `json:"lifetime_value_eur"`
	TotalPurchases   int     `json:"total_purchases"`
}

type crmRiskAlert struct {
	CRMVehicleULID string  `json:"crm_vehicle_ulid"`
	Make           string  `json:"make"`
	Model          string  `json:"model"`
	Year           int     `json:"year"`
	AskingPriceEUR float64 `json:"asking_price_eur"`
	FloorPriceEUR  float64 `json:"floor_price_eur"`
}

type crmUpcomingClose struct {
	DealULID       string  `json:"deal_ulid"`
	Title          string  `json:"title"`
	ContactName    string  `json:"contact_name"`
	DealValueEUR   float64 `json:"deal_value_eur"`
	ExpectedClose  string  `json:"expected_close"`
}

// CRMDashboard GET /api/v1/dealer/crm/dashboard
func (d *Deps) CRMDashboard(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	ctx := r.Context()

	// Inventory counts by status
	invRows, err := d.DB.Query(ctx,
		`SELECT lifecycle_status, count(*) FROM crm_vehicles WHERE entity_ulid=$1 AND lifecycle_status != 'ARCHIVED' GROUP BY lifecycle_status`,
		entityULID)
	inv := crmInventoryStatus{ByStatus: map[string]int{}}
	if err == nil {
		defer invRows.Close()
		for invRows.Next() {
			var st string
			var cnt int
			if invRows.Scan(&st, &cnt) == nil {
				inv.ByStatus[st] = cnt
				inv.Total += cnt
			}
		}
	}

	// Pipeline summary
	var pipeline crmPipelineSummary
	d.DB.QueryRow(ctx,
		`SELECT count(*), coalesce(sum(deal_value_eur),0) FROM crm_deals WHERE entity_ulid=$1 AND status='OPEN'`,
		entityULID).Scan(&pipeline.OpenDeals, &pipeline.PipelineValueEUR)

	// MTD stats
	var mtd crmMTD
	now := time.Now().UTC()
	monthStart := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, time.UTC)
	d.DB.QueryRow(ctx, `
		SELECT
			count(*),
			coalesce(sum(sale_price_eur),0),
			coalesce(avg(
				case when (purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur) > 0
				then (sale_price_eur - (purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur))
				     / (purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur) * 100
				else null end
			),0),
			coalesce(avg(CURRENT_DATE - stock_entry_date),0)
		FROM crm_vehicles
		WHERE entity_ulid=$1 AND lifecycle_status='SOLD' AND sale_date >= $2`,
		entityULID, monthStart).Scan(&mtd.UnitsSold, &mtd.RevenueEUR, &mtd.AvgMarginPct, &mtd.AvgDOM)

	// Top contacts
	topRows, err := d.DB.Query(ctx,
		`SELECT contact_ulid, full_name, lifetime_value_eur, total_purchases FROM crm_contacts WHERE entity_ulid=$1 ORDER BY lifetime_value_eur DESC LIMIT 5`,
		entityULID)
	var topContacts []crmTopContact
	if err == nil {
		defer topRows.Close()
		for topRows.Next() {
			var c crmTopContact
			if topRows.Scan(&c.ContactULID, &c.FullName, &c.LifetimeValueEUR, &c.TotalPurchases) == nil {
				topContacts = append(topContacts, c)
			}
		}
	}
	if topContacts == nil {
		topContacts = []crmTopContact{}
	}

	// Risk alerts: asking < floor * 1.05
	riskRows, err := d.DB.Query(ctx, `
		SELECT crm_vehicle_ulid, make, model, year, asking_price_eur, floor_price_eur
		FROM crm_vehicles
		WHERE entity_ulid=$1
		  AND lifecycle_status IN ('LISTED','READY')
		  AND asking_price_eur IS NOT NULL AND floor_price_eur IS NOT NULL
		  AND asking_price_eur < floor_price_eur * 1.05
		ORDER BY (floor_price_eur - asking_price_eur) DESC LIMIT 5`, entityULID)
	var riskAlerts []crmRiskAlert
	if err == nil {
		defer riskRows.Close()
		for riskRows.Next() {
			var a crmRiskAlert
			if riskRows.Scan(&a.CRMVehicleULID, &a.Make, &a.Model, &a.Year, &a.AskingPriceEUR, &a.FloorPriceEUR) == nil {
				riskAlerts = append(riskAlerts, a)
			}
		}
	}
	if riskAlerts == nil {
		riskAlerts = []crmRiskAlert{}
	}

	// Upcoming closes: deals closing within 7 days
	closeRows, err := d.DB.Query(ctx, `
		SELECT d.deal_ulid, d.title, coalesce(c.full_name,''), coalesce(d.deal_value_eur,0), d.expected_close::text
		FROM crm_deals d
		LEFT JOIN crm_contacts c ON c.contact_ulid = d.contact_ulid
		WHERE d.entity_ulid=$1
		  AND d.status='OPEN'
		  AND d.expected_close BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
		ORDER BY d.expected_close ASC LIMIT 5`, entityULID)
	var upcoming []crmUpcomingClose
	if err == nil {
		defer closeRows.Close()
		for closeRows.Next() {
			var u crmUpcomingClose
			if closeRows.Scan(&u.DealULID, &u.Title, &u.ContactName, &u.DealValueEUR, &u.ExpectedClose) == nil {
				upcoming = append(upcoming, u)
			}
		}
	}
	if upcoming == nil {
		upcoming = []crmUpcomingClose{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"inventory":       inv,
		"pipeline":        pipeline,
		"mtd":             mtd,
		"top_contacts":    topContacts,
		"risk_alerts":     riskAlerts,
		"upcoming_closes": upcoming,
	})
}

// ── CRM Vehicles ──────────────────────────────────────────────────────────────

type crmVehicleRow struct {
	CRMVehicleULID  string   `json:"crm_vehicle_ulid"`
	ItemULID        *string  `json:"item_ulid,omitempty"`
	VIN             *string  `json:"vin,omitempty"`
	Make            string   `json:"make"`
	Model           string   `json:"model"`
	Variant         *string  `json:"variant,omitempty"`
	Year            int      `json:"year"`
	MileageKM       *int     `json:"mileage_km,omitempty"`
	FuelType        *string  `json:"fuel_type,omitempty"`
	Transmission    *string  `json:"transmission,omitempty"`
	ColorExterior   *string  `json:"color_exterior,omitempty"`
	PowerKW         *int     `json:"power_kw,omitempty"`
	CO2GKM          *int     `json:"co2_gkm,omitempty"`
	BodyType        *string  `json:"body_type,omitempty"`
	LifecycleStatus string   `json:"lifecycle_status"`
	PurchasePriceEUR *float64 `json:"purchase_price_eur,omitempty"`
	ReconCostEUR    float64  `json:"recon_cost_eur"`
	TransportCostEUR float64 `json:"transport_cost_eur"`
	HomologationCostEUR float64 `json:"homologation_cost_eur"`
	MarketingCostEUR float64 `json:"marketing_cost_eur"`
	FinancingCostEUR float64 `json:"financing_cost_eur"`
	OtherCostEUR    float64  `json:"other_cost_eur"`
	TotalCostEUR    float64  `json:"total_cost_eur"`
	AskingPriceEUR  *float64 `json:"asking_price_eur,omitempty"`
	FloorPriceEUR   *float64 `json:"floor_price_eur,omitempty"`
	SalePriceEUR    *float64 `json:"sale_price_eur,omitempty"`
	SaleDate        *string  `json:"sale_date,omitempty"`
	ConditionGrade  *string  `json:"condition_grade,omitempty"`
	MainPhotoURL    *string  `json:"main_photo_url,omitempty"`
	StockEntryDate  string   `json:"stock_entry_date"`
	DaysInStock     int      `json:"days_in_stock"`
	MarginEUR       *float64 `json:"margin_eur,omitempty"`
	MarginPct       *float64 `json:"margin_pct,omitempty"`
	Notes           *string  `json:"notes,omitempty"`
	CreatedAt       string   `json:"created_at"`
	UpdatedAt       string   `json:"updated_at"`
}

// CRMVehicleList GET /api/v1/dealer/crm/vehicles
func (d *Deps) CRMVehicleList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	q := r.URL.Query()
	status := q.Get("status")
	search := q.Get("search")
	sortBy := q.Get("sort")
	page := parseInt(q.Get("page"), 1)
	limit := parseInt(q.Get("limit"), 20)
	if limit > 100 {
		limit = 100
	}
	offset := (page - 1) * limit

	args := []any{entityULID}
	where := []string{"v.entity_ulid = $1", "v.lifecycle_status != 'ARCHIVED'"}

	if status != "" {
		args = append(args, status)
		where = append(where, "v.lifecycle_status = $"+itoa(len(args)))
	}
	if search != "" {
		args = append(args, "%"+strings.ToLower(search)+"%")
		where = append(where, "(lower(v.make)||' '||lower(v.model) LIKE $"+itoa(len(args))+" OR lower(coalesce(v.vin,'')) LIKE $"+itoa(len(args))+")")
	}

	orderClause := "v.stock_entry_date DESC"
	switch sortBy {
	case "dom":
		orderClause = "(CURRENT_DATE - v.stock_entry_date) DESC"
	case "price":
		orderClause = "v.asking_price_eur DESC NULLS LAST"
	case "margin":
		orderClause = "((v.asking_price_eur - (v.purchase_price_eur+v.recon_cost_eur+v.transport_cost_eur+v.homologation_cost_eur+v.marketing_cost_eur+v.financing_cost_eur+v.other_cost_eur)) / NULLIF(v.purchase_price_eur+v.recon_cost_eur+v.transport_cost_eur+v.homologation_cost_eur+v.marketing_cost_eur+v.financing_cost_eur+v.other_cost_eur,0) * 100) DESC NULLS LAST"
	}

	whereStr := strings.Join(where, " AND ")
	args = append(args, limit, offset)

	rows, err := d.DB.Query(r.Context(), `
		SELECT v.crm_vehicle_ulid, v.item_ulid, v.vin, v.make, v.model, v.variant, v.year,
		       v.mileage_km, v.fuel_type, v.transmission, v.color_exterior, v.power_kw, v.co2_gkm,
		       v.body_type, v.lifecycle_status,
		       v.purchase_price_eur, v.recon_cost_eur, v.transport_cost_eur,
		       v.homologation_cost_eur, v.marketing_cost_eur, v.financing_cost_eur, v.other_cost_eur,
		       v.asking_price_eur, v.floor_price_eur, v.sale_price_eur, v.sale_date::text,
		       v.condition_grade, v.main_photo_url, v.stock_entry_date::text,
		       (CURRENT_DATE - v.stock_entry_date) AS days_in_stock,
		       v.notes, v.created_at::text, v.updated_at::text
		FROM crm_vehicles v
		WHERE `+whereStr+`
		ORDER BY `+orderClause+`
		LIMIT $`+itoa(len(args)-1)+` OFFSET $`+itoa(len(args)),
		args...)
	if err != nil {
		slog.Error("crm vehicle list", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	var vehicles []crmVehicleRow
	for rows.Next() {
		var v crmVehicleRow
		if err := rows.Scan(
			&v.CRMVehicleULID, &v.ItemULID, &v.VIN, &v.Make, &v.Model, &v.Variant, &v.Year,
			&v.MileageKM, &v.FuelType, &v.Transmission, &v.ColorExterior, &v.PowerKW, &v.CO2GKM,
			&v.BodyType, &v.LifecycleStatus,
			&v.PurchasePriceEUR, &v.ReconCostEUR, &v.TransportCostEUR,
			&v.HomologationCostEUR, &v.MarketingCostEUR, &v.FinancingCostEUR, &v.OtherCostEUR,
			&v.AskingPriceEUR, &v.FloorPriceEUR, &v.SalePriceEUR, &v.SaleDate,
			&v.ConditionGrade, &v.MainPhotoURL, &v.StockEntryDate,
			&v.DaysInStock, &v.Notes, &v.CreatedAt, &v.UpdatedAt,
		); err != nil {
			continue
		}
		v.TotalCostEUR = v.ReconCostEUR + v.TransportCostEUR + v.HomologationCostEUR + v.MarketingCostEUR + v.FinancingCostEUR + v.OtherCostEUR
		if v.PurchasePriceEUR != nil {
			v.TotalCostEUR += *v.PurchasePriceEUR
		}
		if v.AskingPriceEUR != nil && v.TotalCostEUR > 0 {
			m := *v.AskingPriceEUR - v.TotalCostEUR
			p := m / v.TotalCostEUR * 100
			v.MarginEUR = &m
			v.MarginPct = &p
		}
		vehicles = append(vehicles, v)
	}
	if vehicles == nil {
		vehicles = []crmVehicleRow{}
	}

	var total int
	d.DB.QueryRow(r.Context(), "SELECT count(*) FROM crm_vehicles v WHERE "+whereStr, args[:len(args)-2]...).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{"vehicles": vehicles, "total": total, "page": page, "limit": limit})
}

// CRMVehicleCreate POST /api/v1/dealer/crm/vehicles
func (d *Deps) CRMVehicleCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	var req struct {
		VIN                 *string  `json:"vin"`
		Make                string   `json:"make"`
		Model               string   `json:"model"`
		Variant             *string  `json:"variant"`
		Year                int      `json:"year"`
		MileageKM           *int     `json:"mileage_km"`
		FuelType            *string  `json:"fuel_type"`
		Transmission        *string  `json:"transmission"`
		ColorExterior       *string  `json:"color_exterior"`
		PowerKW             *int     `json:"power_kw"`
		CO2GKM              *int     `json:"co2_gkm"`
		BodyType            *string  `json:"body_type"`
		ConditionGrade      *string  `json:"condition_grade"`
		PurchasePriceEUR    *float64 `json:"purchase_price_eur"`
		PurchaseFrom        *string  `json:"purchase_from"`
		PurchaseChannel     *string  `json:"purchase_channel"`
		AskingPriceEUR      *float64 `json:"asking_price_eur"`
		FloorPriceEUR       *float64 `json:"floor_price_eur"`
		TargetMarginPct     *float64 `json:"target_margin_pct"`
		Notes               *string  `json:"notes"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if req.Make == "" || req.Model == "" || req.Year == 0 {
		writeError(w, http.StatusBadRequest, "validation_error", "make, model, year required")
		return
	}

	id := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_vehicles
			(crm_vehicle_ulid, entity_ulid, vin, make, model, variant, year,
			 mileage_km, fuel_type, transmission, color_exterior, power_kw, co2_gkm,
			 body_type, condition_grade, lifecycle_status,
			 purchase_price_eur, purchase_from, purchase_channel,
			 asking_price_eur, floor_price_eur, target_margin_pct, notes)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'SOURCING',$16,$17,$18,$19,$20,$21,$22)`,
		id, entityULID, req.VIN, req.Make, req.Model, req.Variant, req.Year,
		req.MileageKM, req.FuelType, req.Transmission, req.ColorExterior, req.PowerKW, req.CO2GKM,
		req.BodyType, req.ConditionGrade,
		req.PurchasePriceEUR, req.PurchaseFrom, req.PurchaseChannel,
		req.AskingPriceEUR, req.FloorPriceEUR, req.TargetMarginPct, req.Notes)
	if err != nil {
		slog.Error("crm vehicle create", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"crm_vehicle_ulid": id})
}

// CRMVehicleGet GET /api/v1/dealer/crm/vehicles/{ulid}
func (d *Deps) CRMVehicleGet(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	vULID := r.PathValue("ulid")
	if entityULID == "" || vULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	ctx := r.Context()

	var v crmVehicleRow
	var photos []string
	err := d.DB.QueryRow(ctx, `
		SELECT crm_vehicle_ulid, item_ulid, vin, make, model, variant, year,
		       mileage_km, fuel_type, transmission, color_exterior, power_kw, co2_gkm,
		       body_type, lifecycle_status,
		       purchase_price_eur, recon_cost_eur, transport_cost_eur,
		       homologation_cost_eur, marketing_cost_eur, financing_cost_eur, other_cost_eur,
		       asking_price_eur, floor_price_eur, sale_price_eur, sale_date::text,
		       condition_grade, main_photo_url, coalesce(photos,'{}'),
		       stock_entry_date::text, (CURRENT_DATE - stock_entry_date),
		       notes, created_at::text, updated_at::text
		FROM crm_vehicles
		WHERE crm_vehicle_ulid=$1 AND entity_ulid=$2`, vULID, entityULID).Scan(
		&v.CRMVehicleULID, &v.ItemULID, &v.VIN, &v.Make, &v.Model, &v.Variant, &v.Year,
		&v.MileageKM, &v.FuelType, &v.Transmission, &v.ColorExterior, &v.PowerKW, &v.CO2GKM,
		&v.BodyType, &v.LifecycleStatus,
		&v.PurchasePriceEUR, &v.ReconCostEUR, &v.TransportCostEUR,
		&v.HomologationCostEUR, &v.MarketingCostEUR, &v.FinancingCostEUR, &v.OtherCostEUR,
		&v.AskingPriceEUR, &v.FloorPriceEUR, &v.SalePriceEUR, &v.SaleDate,
		&v.ConditionGrade, &v.MainPhotoURL, &photos,
		&v.StockEntryDate, &v.DaysInStock,
		&v.Notes, &v.CreatedAt, &v.UpdatedAt)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "vehicle not found")
		return
	}
	v.TotalCostEUR = v.ReconCostEUR + v.TransportCostEUR + v.HomologationCostEUR + v.MarketingCostEUR + v.FinancingCostEUR + v.OtherCostEUR
	if v.PurchasePriceEUR != nil {
		v.TotalCostEUR += *v.PurchasePriceEUR
	}
	if v.AskingPriceEUR != nil && v.TotalCostEUR > 0 {
		m := *v.AskingPriceEUR - v.TotalCostEUR
		p := m / v.TotalCostEUR * 100
		v.MarginEUR = &m
		v.MarginPct = &p
	}

	// Recon jobs
	type reconJob struct {
		JobULID         string   `json:"job_ulid"`
		JobType         string   `json:"job_type"`
		Description     string   `json:"description"`
		SupplierName    *string  `json:"supplier_name,omitempty"`
		CostEstimateEUR *float64 `json:"cost_estimate_eur,omitempty"`
		CostActualEUR   *float64 `json:"cost_actual_eur,omitempty"`
		Status          string   `json:"status"`
		StartedAt       *string  `json:"started_at,omitempty"`
		CompletedAt     *string  `json:"completed_at,omitempty"`
	}
	reconRows, _ := d.DB.Query(ctx,
		`SELECT job_ulid, job_type, description, supplier_name, cost_estimate_eur, cost_actual_eur, status, started_at::text, completed_at::text FROM crm_recon_jobs WHERE crm_vehicle_ulid=$1 ORDER BY created_at DESC`, vULID)
	var recon []reconJob
	if reconRows != nil {
		defer reconRows.Close()
		for reconRows.Next() {
			var j reconJob
			if reconRows.Scan(&j.JobULID, &j.JobType, &j.Description, &j.SupplierName, &j.CostEstimateEUR, &j.CostActualEUR, &j.Status, &j.StartedAt, &j.CompletedAt) == nil {
				recon = append(recon, j)
			}
		}
	}
	if recon == nil {
		recon = []reconJob{}
	}

	// Transactions
	type txRow struct {
		TxULID        string  `json:"tx_ulid"`
		TxType        string  `json:"tx_type"`
		AmountEUR     float64 `json:"amount_eur"`
		Description   *string `json:"description,omitempty"`
		TxDate        string  `json:"tx_date"`
	}
	txRows, _ := d.DB.Query(ctx,
		`SELECT tx_ulid, tx_type, amount_eur, description, tx_date::text FROM crm_transactions WHERE crm_vehicle_ulid=$1 ORDER BY tx_date DESC`, vULID)
	var txs []txRow
	if txRows != nil {
		defer txRows.Close()
		for txRows.Next() {
			var t txRow
			if txRows.Scan(&t.TxULID, &t.TxType, &t.AmountEUR, &t.Description, &t.TxDate) == nil {
				txs = append(txs, t)
			}
		}
	}
	if txs == nil {
		txs = []txRow{}
	}

	// Recent communications
	type commRow struct {
		CommULID  string  `json:"comm_ulid"`
		Channel   string  `json:"channel"`
		Direction *string `json:"direction,omitempty"`
		Subject   *string `json:"subject,omitempty"`
		Outcome   *string `json:"outcome,omitempty"`
		CreatedAt string  `json:"created_at"`
	}
	commRows, _ := d.DB.Query(ctx,
		`SELECT comm_ulid, channel, direction, subject, outcome, created_at::text FROM crm_communications WHERE crm_vehicle_ulid=$1 ORDER BY created_at DESC LIMIT 20`, vULID)
	var comms []commRow
	if commRows != nil {
		defer commRows.Close()
		for commRows.Next() {
			var c commRow
			if commRows.Scan(&c.CommULID, &c.Channel, &c.Direction, &c.Subject, &c.Outcome, &c.CreatedAt) == nil {
				comms = append(comms, c)
			}
		}
	}
	if comms == nil {
		comms = []commRow{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"vehicle":        v,
		"photos":         photos,
		"recon_jobs":     recon,
		"transactions":   txs,
		"communications": comms,
	})
}

// CRMVehicleUpdate PUT /api/v1/dealer/crm/vehicles/{ulid}
func (d *Deps) CRMVehicleUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	vULID := r.PathValue("ulid")
	if entityULID == "" || vULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	var req map[string]any
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}

	allowed := map[string]bool{
		"vin": true, "make": true, "model": true, "variant": true, "year": true,
		"mileage_km": true, "fuel_type": true, "transmission": true, "color_exterior": true,
		"color_interior": true, "power_kw": true, "co2_gkm": true, "body_type": true,
		"lifecycle_status": true, "purchase_price_eur": true, "purchase_from": true,
		"purchase_channel": true, "purchase_date": true, "recon_cost_eur": true,
		"transport_cost_eur": true, "homologation_cost_eur": true, "marketing_cost_eur": true,
		"financing_cost_eur": true, "other_cost_eur": true, "asking_price_eur": true,
		"floor_price_eur": true, "target_margin_pct": true, "sale_price_eur": true,
		"sale_date": true, "sale_contact_ulid": true, "payment_method": true,
		"condition_grade": true, "notes": true, "main_photo_url": true,
		"service_book": true, "keys_count": true,
	}

	setClauses := []string{}
	args := []any{}
	for k, v := range req {
		if !allowed[k] {
			continue
		}
		args = append(args, v)
		setClauses = append(setClauses, k+"=$"+itoa(len(args)))
	}
	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no updatable fields provided")
		return
	}
	args = append(args, vULID, entityULID)
	_, err := d.DB.Exec(r.Context(),
		"UPDATE crm_vehicles SET "+strings.Join(setClauses, ",")+", updated_at=now() WHERE crm_vehicle_ulid=$"+itoa(len(args)-1)+" AND entity_ulid=$"+itoa(len(args)),
		args...)
	if err != nil {
		slog.Error("crm vehicle update", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// CRMVehicleDelete DELETE /api/v1/dealer/crm/vehicles/{ulid}
func (d *Deps) CRMVehicleDelete(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	vULID := r.PathValue("ulid")
	if entityULID == "" || vULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	_, err := d.DB.Exec(r.Context(),
		"UPDATE crm_vehicles SET lifecycle_status='ARCHIVED', updated_at=now() WHERE crm_vehicle_ulid=$1 AND entity_ulid=$2",
		vULID, entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "archived"})
}

// ── CRM Contacts ──────────────────────────────────────────────────────────────

type crmContactRow struct {
	ContactULID      string   `json:"contact_ulid"`
	FullName         string   `json:"full_name"`
	Email            *string  `json:"email,omitempty"`
	Phone            *string  `json:"phone,omitempty"`
	PhoneAlt         *string  `json:"phone_alt,omitempty"`
	AddressCity      *string  `json:"address_city,omitempty"`
	AddressCountry   *string  `json:"address_country,omitempty"`
	PreferredContact *string  `json:"preferred_contact,omitempty"`
	Language         *string  `json:"language,omitempty"`
	Tags             []string `json:"tags"`
	Notes            *string  `json:"notes,omitempty"`
	Source           *string  `json:"source,omitempty"`
	GDPRConsent      bool     `json:"gdpr_consent"`
	LifetimeValueEUR float64  `json:"lifetime_value_eur"`
	TotalPurchases   int      `json:"total_purchases"`
	TotalInquiries   int      `json:"total_inquiries"`
	LastContactAt    *string  `json:"last_contact_at,omitempty"`
	CreatedAt        string   `json:"created_at"`
}

// CRMContactList GET /api/v1/dealer/crm/contacts
func (d *Deps) CRMContactList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	q := r.URL.Query()
	search := q.Get("q")
	page := parseInt(q.Get("page"), 1)
	limit := parseInt(q.Get("limit"), 20)
	if limit > 100 {
		limit = 100
	}
	offset := (page - 1) * limit

	args := []any{entityULID}
	where := "entity_ulid = $1"
	if search != "" {
		args = append(args, "%"+strings.ToLower(search)+"%")
		n := itoa(len(args))
		where += " AND (lower(full_name) LIKE $" + n + " OR lower(coalesce(email,'')) LIKE $" + n + " OR lower(coalesce(phone,'')) LIKE $" + n + ")"
	}

	args = append(args, limit, offset)
	rows, err := d.DB.Query(r.Context(), `
		SELECT contact_ulid, full_name, email, phone, phone_alt, address_city, address_country,
		       preferred_contact, language, coalesce(tags,'{}'), notes, source,
		       gdpr_consent, lifetime_value_eur, total_purchases, total_inquiries,
		       last_contact_at::text, created_at::text
		FROM crm_contacts
		WHERE `+where+`
		ORDER BY last_contact_at DESC NULLS LAST, created_at DESC
		LIMIT $`+itoa(len(args)-1)+` OFFSET $`+itoa(len(args)),
		args...)
	if err != nil {
		slog.Error("crm contact list", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	var contacts []crmContactRow
	for rows.Next() {
		var c crmContactRow
		if rows.Scan(&c.ContactULID, &c.FullName, &c.Email, &c.Phone, &c.PhoneAlt,
			&c.AddressCity, &c.AddressCountry, &c.PreferredContact, &c.Language, &c.Tags,
			&c.Notes, &c.Source, &c.GDPRConsent, &c.LifetimeValueEUR,
			&c.TotalPurchases, &c.TotalInquiries, &c.LastContactAt, &c.CreatedAt) == nil {
			contacts = append(contacts, c)
		}
	}
	if contacts == nil {
		contacts = []crmContactRow{}
	}

	var total int
	d.DB.QueryRow(r.Context(), "SELECT count(*) FROM crm_contacts WHERE "+where, args[:len(args)-2]...).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"contacts": contacts, "total": total, "page": page})
}

// CRMContactCreate POST /api/v1/dealer/crm/contacts
func (d *Deps) CRMContactCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	var req struct {
		FullName         string   `json:"full_name"`
		Email            *string  `json:"email"`
		Phone            *string  `json:"phone"`
		PhoneAlt         *string  `json:"phone_alt"`
		AddressCity      *string  `json:"address_city"`
		AddressCountry   *string  `json:"address_country"`
		PreferredContact *string  `json:"preferred_contact"`
		Language         *string  `json:"language"`
		Tags             []string `json:"tags"`
		Notes            *string  `json:"notes"`
		Source           *string  `json:"source"`
		GDPRConsent      bool     `json:"gdpr_consent"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if req.FullName == "" {
		writeError(w, http.StatusBadRequest, "validation_error", "full_name required")
		return
	}
	id := ulid.Make().String()
	var gdprAt *time.Time
	if req.GDPRConsent {
		now := time.Now().UTC()
		gdprAt = &now
	}
	tags := req.Tags
	if tags == nil {
		tags = []string{}
	}
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_contacts
			(contact_ulid, entity_ulid, full_name, email, phone, phone_alt,
			 address_city, address_country, preferred_contact, language, tags,
			 notes, source, gdpr_consent, gdpr_consent_at, vault_dek_id)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
		id, entityULID, req.FullName, req.Email, req.Phone, req.PhoneAlt,
		req.AddressCity, req.AddressCountry, req.PreferredContact, req.Language, tags,
		req.Notes, req.Source, req.GDPRConsent, gdprAt, "dek:"+entityULID)
	if err != nil {
		slog.Error("crm contact create", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"contact_ulid": id})
}

// CRMContactGet GET /api/v1/dealer/crm/contacts/{ulid}
func (d *Deps) CRMContactGet(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	cULID := r.PathValue("ulid")
	if entityULID == "" || cULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	ctx := r.Context()
	var c crmContactRow
	err := d.DB.QueryRow(ctx, `
		SELECT contact_ulid, full_name, email, phone, phone_alt, address_city, address_country,
		       preferred_contact, language, coalesce(tags,'{}'), notes, source,
		       gdpr_consent, lifetime_value_eur, total_purchases, total_inquiries,
		       last_contact_at::text, created_at::text
		FROM crm_contacts WHERE contact_ulid=$1 AND entity_ulid=$2`, cULID, entityULID).Scan(
		&c.ContactULID, &c.FullName, &c.Email, &c.Phone, &c.PhoneAlt,
		&c.AddressCity, &c.AddressCountry, &c.PreferredContact, &c.Language, &c.Tags,
		&c.Notes, &c.Source, &c.GDPRConsent, &c.LifetimeValueEUR,
		&c.TotalPurchases, &c.TotalInquiries, &c.LastContactAt, &c.CreatedAt)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "contact not found")
		return
	}

	// Linked deals
	type dealBrief struct {
		DealULID     string  `json:"deal_ulid"`
		Title        string  `json:"title"`
		Status       string  `json:"status"`
		DealValueEUR float64 `json:"deal_value_eur"`
		CreatedAt    string  `json:"created_at"`
	}
	dRows, _ := d.DB.Query(ctx,
		`SELECT deal_ulid, title, status, coalesce(deal_value_eur,0), created_at::text FROM crm_deals WHERE contact_ulid=$1 AND entity_ulid=$2 ORDER BY created_at DESC LIMIT 10`,
		cULID, entityULID)
	var deals []dealBrief
	if dRows != nil {
		defer dRows.Close()
		for dRows.Next() {
			var dl dealBrief
			if dRows.Scan(&dl.DealULID, &dl.Title, &dl.Status, &dl.DealValueEUR, &dl.CreatedAt) == nil {
				deals = append(deals, dl)
			}
		}
	}
	if deals == nil {
		deals = []dealBrief{}
	}

	// Last 10 communications
	type commBrief struct {
		CommULID  string  `json:"comm_ulid"`
		Channel   string  `json:"channel"`
		Subject   *string `json:"subject,omitempty"`
		Outcome   *string `json:"outcome,omitempty"`
		CreatedAt string  `json:"created_at"`
	}
	cRows, _ := d.DB.Query(ctx,
		`SELECT comm_ulid, channel, subject, outcome, created_at::text FROM crm_communications WHERE contact_ulid=$1 AND entity_ulid=$2 ORDER BY created_at DESC LIMIT 10`,
		cULID, entityULID)
	var comms []commBrief
	if cRows != nil {
		defer cRows.Close()
		for cRows.Next() {
			var cm commBrief
			if cRows.Scan(&cm.CommULID, &cm.Channel, &cm.Subject, &cm.Outcome, &cm.CreatedAt) == nil {
				comms = append(comms, cm)
			}
		}
	}
	if comms == nil {
		comms = []commBrief{}
	}

	writeJSON(w, http.StatusOK, map[string]any{"contact": c, "deals": deals, "communications": comms})
}

// CRMContactUpdate PUT /api/v1/dealer/crm/contacts/{ulid}
func (d *Deps) CRMContactUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	cULID := r.PathValue("ulid")
	if entityULID == "" || cULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	var req map[string]any
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	allowed := map[string]bool{
		"full_name": true, "email": true, "phone": true, "phone_alt": true,
		"address_line1": true, "address_city": true, "address_country": true, "postal_code": true,
		"preferred_contact": true, "language": true, "tags": true, "notes": true,
		"source": true, "gdpr_consent": true,
	}
	setClauses := []string{}
	args := []any{}
	for k, v := range req {
		if !allowed[k] {
			continue
		}
		args = append(args, v)
		setClauses = append(setClauses, k+"=$"+itoa(len(args)))
	}
	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no updatable fields provided")
		return
	}
	args = append(args, cULID, entityULID)
	_, err := d.DB.Exec(r.Context(),
		"UPDATE crm_contacts SET "+strings.Join(setClauses, ",")+", updated_at=now() WHERE contact_ulid=$"+itoa(len(args)-1)+" AND entity_ulid=$"+itoa(len(args)),
		args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// ── Pipeline / Deals ──────────────────────────────────────────────────────────

func (d *Deps) ensureDefaultPipelineStages(entityULID string) {
	var cnt int
	d.DB.QueryRow(context.Background(), "SELECT count(*) FROM crm_pipeline_stages WHERE entity_ulid=$1", entityULID).Scan(&cnt) //nolint
	if cnt > 0 {
		return
	}
	defaults := []struct {
		name, color string
		pos         int
		isWon, isLost bool
	}{
		{"Lead", "#8b5cf6", 1, false, false},
		{"Contacted", "#3b82f6", 2, false, false},
		{"Offer Made", "#f59e0b", 3, false, false},
		{"Negotiating", "#f97316", 4, false, false},
		{"Won", "#15b570", 5, true, false},
		{"Lost", "#ef4444", 6, false, true},
	}
	for _, s := range defaults {
		d.DB.Exec(context.Background(), //nolint
			`INSERT INTO crm_pipeline_stages (stage_ulid, entity_ulid, name, color, position, is_won, is_lost) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
			ulid.Make().String(), entityULID, s.name, s.color, s.pos, s.isWon, s.isLost)
	}
}

// CRMPipelineStages GET /api/v1/dealer/crm/pipeline/stages
func (d *Deps) CRMPipelineStages(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	d.ensureDefaultPipelineStages(entityULID)

	rows, err := d.DB.Query(r.Context(), `
		SELECT s.stage_ulid, s.name, s.color, s.position, s.is_won, s.is_lost,
		       count(dl.deal_ulid) AS deal_count
		FROM crm_pipeline_stages s
		LEFT JOIN crm_deals dl ON dl.stage_ulid = s.stage_ulid AND dl.status = 'OPEN'
		WHERE s.entity_ulid = $1
		GROUP BY s.stage_ulid, s.name, s.color, s.position, s.is_won, s.is_lost
		ORDER BY s.position`, entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type stageRow struct {
		StageULID string `json:"stage_ulid"`
		Name      string `json:"name"`
		Color     string `json:"color"`
		Position  int    `json:"position"`
		IsWon     bool   `json:"is_won"`
		IsLost    bool   `json:"is_lost"`
		DealCount int    `json:"deal_count"`
	}
	var stages []stageRow
	for rows.Next() {
		var s stageRow
		if rows.Scan(&s.StageULID, &s.Name, &s.Color, &s.Position, &s.IsWon, &s.IsLost, &s.DealCount) == nil {
			stages = append(stages, s)
		}
	}
	if stages == nil {
		stages = []stageRow{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"stages": stages})
}

// CRMPipelineKanban GET /api/v1/dealer/crm/pipeline/kanban
func (d *Deps) CRMPipelineKanban(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	d.ensureDefaultPipelineStages(entityULID)
	ctx := r.Context()

	type dealCard struct {
		DealULID          string  `json:"deal_ulid"`
		Title             string  `json:"title"`
		ContactName       string  `json:"contact_name"`
		VehicleLabel      string  `json:"vehicle_label"`
		DealValueEUR      float64 `json:"deal_value_eur"`
		ProbabilityPct    int     `json:"probability_pct"`
		DaysSinceLastComm int     `json:"days_since_last_comm"`
	}
	type kanbanStage struct {
		StageULID string     `json:"stage_ulid"`
		Name      string     `json:"name"`
		Color     string     `json:"color"`
		Position  int        `json:"position"`
		IsWon     bool       `json:"is_won"`
		IsLost    bool       `json:"is_lost"`
		DealCount int        `json:"deal_count"`
		Deals     []dealCard `json:"deals"`
	}

	stageRows, err := d.DB.Query(ctx,
		`SELECT stage_ulid, name, color, position, is_won, is_lost FROM crm_pipeline_stages WHERE entity_ulid=$1 ORDER BY position`,
		entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer stageRows.Close()

	var kanban []kanbanStage
	for stageRows.Next() {
		var s kanbanStage
		if stageRows.Scan(&s.StageULID, &s.Name, &s.Color, &s.Position, &s.IsWon, &s.IsLost) != nil {
			continue
		}
		dRows, _ := d.DB.Query(ctx, `
			SELECT d.deal_ulid, d.title,
			       coalesce(c.full_name,''),
			       coalesce(v.make||' '||v.model||' '||v.year::text,''),
			       coalesce(d.deal_value_eur,0),
			       coalesce(d.probability_pct,50),
			       coalesce((CURRENT_DATE - max(cm.created_at)::date), 999)
			FROM crm_deals d
			LEFT JOIN crm_contacts c ON c.contact_ulid = d.contact_ulid
			LEFT JOIN crm_vehicles v ON v.crm_vehicle_ulid = d.crm_vehicle_ulid
			LEFT JOIN crm_communications cm ON cm.deal_ulid = d.deal_ulid
			WHERE d.stage_ulid = $1 AND d.entity_ulid = $2 AND d.status = 'OPEN'
			GROUP BY d.deal_ulid, d.title, c.full_name, v.make, v.model, v.year, d.deal_value_eur, d.probability_pct
			ORDER BY d.updated_at DESC`, s.StageULID, entityULID)
		if dRows != nil {
			defer dRows.Close()
			for dRows.Next() {
				var dc dealCard
				if dRows.Scan(&dc.DealULID, &dc.Title, &dc.ContactName, &dc.VehicleLabel,
					&dc.DealValueEUR, &dc.ProbabilityPct, &dc.DaysSinceLastComm) == nil {
					s.Deals = append(s.Deals, dc)
				}
			}
		}
		if s.Deals == nil {
			s.Deals = []dealCard{}
		}
		s.DealCount = len(s.Deals)
		kanban = append(kanban, s)
	}
	if kanban == nil {
		kanban = []kanbanStage{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"stages": kanban})
}

// CRMDealList GET /api/v1/dealer/crm/deals
func (d *Deps) CRMDealList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	q := r.URL.Query()
	stageFilter := q.Get("stage")
	statusFilter := q.Get("status")
	if statusFilter == "" {
		statusFilter = "OPEN"
	}
	page := parseInt(q.Get("page"), 1)
	limit := parseInt(q.Get("limit"), 20)
	offset := (page - 1) * limit

	args := []any{entityULID, statusFilter}
	where := "d.entity_ulid=$1 AND d.status=$2"
	if stageFilter != "" {
		args = append(args, stageFilter)
		where += " AND d.stage_ulid=$" + itoa(len(args))
	}
	args = append(args, limit, offset)

	rows, err := d.DB.Query(r.Context(), `
		SELECT d.deal_ulid, d.title, d.status, coalesce(d.deal_value_eur,0),
		       coalesce(d.probability_pct,50), d.expected_close::text, d.lost_reason,
		       coalesce(c.full_name,''), coalesce(v.make||' '||v.model,''),
		       s.name, s.color, d.created_at::text, d.updated_at::text
		FROM crm_deals d
		LEFT JOIN crm_contacts c ON c.contact_ulid = d.contact_ulid
		LEFT JOIN crm_vehicles v ON v.crm_vehicle_ulid = d.crm_vehicle_ulid
		LEFT JOIN crm_pipeline_stages s ON s.stage_ulid = d.stage_ulid
		WHERE `+where+` ORDER BY d.updated_at DESC LIMIT $`+itoa(len(args)-1)+` OFFSET $`+itoa(len(args)),
		args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type dealRow struct {
		DealULID      string  `json:"deal_ulid"`
		Title         string  `json:"title"`
		Status        string  `json:"status"`
		DealValueEUR  float64 `json:"deal_value_eur"`
		ProbabilityPct int    `json:"probability_pct"`
		ExpectedClose *string `json:"expected_close,omitempty"`
		LostReason    *string `json:"lost_reason,omitempty"`
		ContactName   string  `json:"contact_name"`
		VehicleLabel  string  `json:"vehicle_label"`
		StageName     string  `json:"stage_name"`
		StageColor    string  `json:"stage_color"`
		CreatedAt     string  `json:"created_at"`
		UpdatedAt     string  `json:"updated_at"`
	}
	var deals []dealRow
	for rows.Next() {
		var dl dealRow
		if rows.Scan(&dl.DealULID, &dl.Title, &dl.Status, &dl.DealValueEUR, &dl.ProbabilityPct,
			&dl.ExpectedClose, &dl.LostReason, &dl.ContactName, &dl.VehicleLabel,
			&dl.StageName, &dl.StageColor, &dl.CreatedAt, &dl.UpdatedAt) == nil {
			deals = append(deals, dl)
		}
	}
	if deals == nil {
		deals = []dealRow{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"deals": deals, "page": page})
}

// CRMDealCreate POST /api/v1/dealer/crm/deals
func (d *Deps) CRMDealCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	d.ensureDefaultPipelineStages(entityULID)
	var req struct {
		ContactULID    string   `json:"contact_ulid"`
		CRMVehicleULID *string  `json:"crm_vehicle_ulid"`
		StageULID      string   `json:"stage_ulid"`
		Title          string   `json:"title"`
		DealValueEUR   *float64 `json:"deal_value_eur"`
		ProbabilityPct *int     `json:"probability_pct"`
		ExpectedClose  *string  `json:"expected_close"`
		Notes          *string  `json:"notes"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if req.Title == "" || req.ContactULID == "" {
		writeError(w, http.StatusBadRequest, "validation_error", "title and contact_ulid required")
		return
	}
	if req.StageULID == "" {
		d.DB.QueryRow(r.Context(), `SELECT stage_ulid FROM crm_pipeline_stages WHERE entity_ulid=$1 ORDER BY position LIMIT 1`, entityULID).Scan(&req.StageULID)
	}
	id := ulid.Make().String()
	userULID := middleware.GetDealerULID(r.Context())
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_deals (deal_ulid, entity_ulid, contact_ulid, crm_vehicle_ulid, stage_ulid, title, deal_value_eur, probability_pct, expected_close, notes, assigned_to)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
		id, entityULID, req.ContactULID, req.CRMVehicleULID, req.StageULID,
		req.Title, req.DealValueEUR, req.ProbabilityPct, req.ExpectedClose, req.Notes, userULID)
	if err != nil {
		slog.Error("crm deal create", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"deal_ulid": id})
}

// CRMDealUpdate PUT /api/v1/dealer/crm/deals/{ulid}
func (d *Deps) CRMDealUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	dULID := r.PathValue("ulid")
	if entityULID == "" || dULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	var req map[string]any
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	allowed := map[string]bool{"stage_ulid": true, "status": true, "probability_pct": true, "deal_value_eur": true, "expected_close": true, "lost_reason": true, "notes": true}
	setClauses := []string{}
	args := []any{}
	for k, v := range req {
		if !allowed[k] { continue }
		args = append(args, v)
		setClauses = append(setClauses, k+"=$"+itoa(len(args)))
	}
	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no updatable fields")
		return
	}
	args = append(args, dULID, entityULID)
	_, err := d.DB.Exec(r.Context(),
		"UPDATE crm_deals SET "+strings.Join(setClauses, ",")+", updated_at=now() WHERE deal_ulid=$"+itoa(len(args)-1)+" AND entity_ulid=$"+itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// ── Communications ────────────────────────────────────────────────────────────

// CRMCommCreate POST /api/v1/dealer/crm/communications
func (d *Deps) CRMCommCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	var req struct {
		ContactULID    *string `json:"contact_ulid"`
		DealULID       *string `json:"deal_ulid"`
		CRMVehicleULID *string `json:"crm_vehicle_ulid"`
		Channel        string  `json:"channel"`
		Direction      *string `json:"direction"`
		Subject        *string `json:"subject"`
		Body           *string `json:"body"`
		Outcome        *string `json:"outcome"`
		DurationSec    *int    `json:"duration_sec"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if req.Channel == "" {
		writeError(w, http.StatusBadRequest, "validation_error", "channel required")
		return
	}
	id := ulid.Make().String()
	userULID := middleware.GetDealerULID(r.Context())
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_communications (comm_ulid, entity_ulid, contact_ulid, deal_ulid, crm_vehicle_ulid, channel, direction, subject, body, outcome, duration_sec, created_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
		id, entityULID, req.ContactULID, req.DealULID, req.CRMVehicleULID,
		req.Channel, req.Direction, req.Subject, req.Body, req.Outcome, req.DurationSec, userULID)
	if err != nil {
		slog.Error("crm comm create", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	if req.ContactULID != nil {
		d.DB.Exec(r.Context(), //nolint
			"UPDATE crm_contacts SET last_contact_at=now(), total_inquiries=total_inquiries+1 WHERE contact_ulid=$1 AND entity_ulid=$2",
			*req.ContactULID, entityULID)
	}
	writeJSON(w, http.StatusCreated, map[string]string{"comm_ulid": id})
}

// CRMCommList GET /api/v1/dealer/crm/communications
func (d *Deps) CRMCommList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	q := r.URL.Query()
	limit := parseInt(q.Get("limit"), 50)
	if limit > 200 { limit = 200 }
	args := []any{entityULID}
	where := "entity_ulid=$1"
	if cULID := q.Get("contact_ulid"); cULID != "" {
		args = append(args, cULID)
		where += " AND contact_ulid=$" + itoa(len(args))
	}
	if dULID := q.Get("deal_ulid"); dULID != "" {
		args = append(args, dULID)
		where += " AND deal_ulid=$" + itoa(len(args))
	}
	args = append(args, limit)
	rows, err := d.DB.Query(r.Context(),
		`SELECT comm_ulid, channel, direction, subject, body, outcome, duration_sec, created_at::text FROM crm_communications WHERE `+where+` ORDER BY created_at DESC LIMIT $`+itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()
	type commRow struct {
		CommULID    string  `json:"comm_ulid"`
		Channel     string  `json:"channel"`
		Direction   *string `json:"direction,omitempty"`
		Subject     *string `json:"subject,omitempty"`
		Body        *string `json:"body,omitempty"`
		Outcome     *string `json:"outcome,omitempty"`
		DurationSec *int    `json:"duration_sec,omitempty"`
		CreatedAt   string  `json:"created_at"`
	}
	var comms []commRow
	for rows.Next() {
		var c commRow
		if rows.Scan(&c.CommULID, &c.Channel, &c.Direction, &c.Subject, &c.Body, &c.Outcome, &c.DurationSec, &c.CreatedAt) == nil {
			comms = append(comms, c)
		}
	}
	if comms == nil { comms = []commRow{} }
	writeJSON(w, http.StatusOK, map[string]any{"communications": comms})
}

// ── Reconditioning ────────────────────────────────────────────────────────────

// CRMReconCreate POST /api/v1/dealer/crm/recon
func (d *Deps) CRMReconCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	var req struct {
		CRMVehicleULID  string   `json:"crm_vehicle_ulid"`
		JobType         string   `json:"job_type"`
		Description     string   `json:"description"`
		SupplierName    *string  `json:"supplier_name"`
		CostEstimateEUR *float64 `json:"cost_estimate_eur"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if req.CRMVehicleULID == "" || req.JobType == "" || req.Description == "" {
		writeError(w, http.StatusBadRequest, "validation_error", "crm_vehicle_ulid, job_type, description required")
		return
	}
	id := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_recon_jobs (job_ulid, crm_vehicle_ulid, entity_ulid, job_type, description, supplier_name, cost_estimate_eur)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		id, req.CRMVehicleULID, entityULID, req.JobType, req.Description, req.SupplierName, req.CostEstimateEUR)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	if req.CostEstimateEUR != nil {
		d.DB.Exec(r.Context(), //nolint
			"UPDATE crm_vehicles SET recon_cost_eur=recon_cost_eur+$1, updated_at=now() WHERE crm_vehicle_ulid=$2 AND entity_ulid=$3",
			*req.CostEstimateEUR, req.CRMVehicleULID, entityULID)
	}
	writeJSON(w, http.StatusCreated, map[string]string{"job_ulid": id})
}

// CRMReconUpdate PUT /api/v1/dealer/crm/recon/{job_ulid}
func (d *Deps) CRMReconUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	jobULID := r.PathValue("job_ulid")
	if entityULID == "" || jobULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	var req struct {
		Status        *string  `json:"status"`
		CostActualEUR *float64 `json:"cost_actual_eur"`
		StartedAt     *string  `json:"started_at"`
		CompletedAt   *string  `json:"completed_at"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	var vULID string
	d.DB.QueryRow(r.Context(), "SELECT crm_vehicle_ulid FROM crm_recon_jobs WHERE job_ulid=$1 AND entity_ulid=$2", jobULID, entityULID).Scan(&vULID)

	setClauses := []string{}
	args := []any{}
	if req.Status != nil        { args = append(args, *req.Status);        setClauses = append(setClauses, "status=$"+itoa(len(args))) }
	if req.CostActualEUR != nil { args = append(args, *req.CostActualEUR); setClauses = append(setClauses, "cost_actual_eur=$"+itoa(len(args))) }
	if req.StartedAt != nil     { args = append(args, *req.StartedAt);     setClauses = append(setClauses, "started_at=$"+itoa(len(args))) }
	if req.CompletedAt != nil   { args = append(args, *req.CompletedAt);   setClauses = append(setClauses, "completed_at=$"+itoa(len(args))) }
	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no fields to update")
		return
	}
	args = append(args, jobULID, entityULID)
	_, err := d.DB.Exec(r.Context(),
		"UPDATE crm_recon_jobs SET "+strings.Join(setClauses, ",")+
			" WHERE job_ulid=$"+itoa(len(args)-1)+" AND entity_ulid=$"+itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	if req.Status != nil && *req.Status == "DONE" && vULID != "" {
		d.DB.Exec(r.Context(), //nolint
			`UPDATE crm_vehicles SET recon_cost_eur=(SELECT coalesce(sum(coalesce(cost_actual_eur,cost_estimate_eur,0)),0) FROM crm_recon_jobs WHERE crm_vehicle_ulid=$1 AND status='DONE'), updated_at=now() WHERE crm_vehicle_ulid=$1 AND entity_ulid=$2`,
			vULID, entityULID)
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// ── Financial P&L ─────────────────────────────────────────────────────────────

// CRMFinancialPnL GET /api/v1/dealer/crm/financial/pnl
func (d *Deps) CRMFinancialPnL(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	ctx := r.Context()
	q := r.URL.Query()

	if vULID := q.Get("vehicle_ulid"); vULID != "" {
		var make_, model string
		var year, dom int
		var totalCost float64
		var salePrice *float64
		err := d.DB.QueryRow(ctx, `
			SELECT make, model, year,
			       coalesce(purchase_price_eur,0)+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur,
			       sale_price_eur, (CURRENT_DATE - stock_entry_date)
			FROM crm_vehicles WHERE crm_vehicle_ulid=$1 AND entity_ulid=$2`, vULID, entityULID).
			Scan(&make_, &model, &year, &totalCost, &salePrice, &dom)
		if err != nil {
			writeError(w, http.StatusNotFound, "not_found", "vehicle not found")
			return
		}
		result := map[string]any{"make": make_, "model": model, "year": year, "total_cost_eur": totalCost, "days_in_stock": dom}
		if salePrice != nil {
			gp := *salePrice - totalCost
			result["sale_price_eur"] = *salePrice
			result["gross_profit_eur"] = gp
			if totalCost > 0 { result["margin_pct"] = gp / totalCost * 100 }
		}
		type txRow struct {
			TxULID      string  `json:"tx_ulid"`
			TxType      string  `json:"tx_type"`
			AmountEUR   float64 `json:"amount_eur"`
			Description *string `json:"description,omitempty"`
			TxDate      string  `json:"tx_date"`
		}
		txRows, _ := d.DB.Query(ctx, `SELECT tx_ulid, tx_type, amount_eur, description, tx_date::text FROM crm_transactions WHERE crm_vehicle_ulid=$1 ORDER BY tx_date DESC`, vULID)
		var txs []txRow
		if txRows != nil {
			defer txRows.Close()
			for txRows.Next() {
				var t txRow
				if txRows.Scan(&t.TxULID, &t.TxType, &t.AmountEUR, &t.Description, &t.TxDate) == nil {
					txs = append(txs, t)
				}
			}
		}
		if txs == nil { txs = []txRow{} }
		writeJSON(w, http.StatusOK, map[string]any{"vehicle": result, "transactions": txs})
		return
	}

	period := q.Get("period")
	if period == "" { period = time.Now().UTC().Format("2006-01") }
	periodStart := period + "-01"

	type vPnL struct {
		CRMVehicleULID string  `json:"crm_vehicle_ulid"`
		Make           string  `json:"make"`
		Model          string  `json:"model"`
		Year           int     `json:"year"`
		TotalCostEUR   float64 `json:"total_cost_eur"`
		SalePriceEUR   float64 `json:"sale_price_eur"`
		GrossProfitEUR float64 `json:"gross_profit_eur"`
		MarginPct      float64 `json:"margin_pct"`
		DaysInStock    int     `json:"days_in_stock"`
	}
	vRows, err := d.DB.Query(ctx, `
		SELECT crm_vehicle_ulid, make, model, year,
		       coalesce(purchase_price_eur,0)+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur,
		       coalesce(sale_price_eur,0), (CURRENT_DATE - stock_entry_date)
		FROM crm_vehicles WHERE entity_ulid=$1 AND lifecycle_status='SOLD'
		  AND sale_date >= $2::date AND sale_date < $2::date + INTERVAL '1 month'
		ORDER BY sale_date DESC`, entityULID, periodStart)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer vRows.Close()

	var vehicles []vPnL
	var totalRevenue, totalCosts, marginSum, domSum float64
	for vRows.Next() {
		var v vPnL
		if vRows.Scan(&v.CRMVehicleULID, &v.Make, &v.Model, &v.Year, &v.TotalCostEUR, &v.SalePriceEUR, &v.DaysInStock) != nil { continue }
		v.GrossProfitEUR = v.SalePriceEUR - v.TotalCostEUR
		if v.TotalCostEUR > 0 { v.MarginPct = v.GrossProfitEUR / v.TotalCostEUR * 100 }
		totalRevenue += v.SalePriceEUR
		totalCosts += v.TotalCostEUR
		marginSum += v.MarginPct
		domSum += float64(v.DaysInStock)
		vehicles = append(vehicles, v)
	}
	if vehicles == nil { vehicles = []vPnL{} }
	n := len(vehicles)
	avgMargin, avgDOM := 0.0, 0.0
	if n > 0 { avgMargin = marginSum / float64(n); avgDOM = domSum / float64(n) }
	grossProfit := totalRevenue - totalCosts
	totalMarginPct := 0.0
	if totalCosts > 0 { totalMarginPct = grossProfit / totalCosts * 100 }
	avgPerUnit := 0.0
	if n > 0 { avgPerUnit = grossProfit / float64(n) }

	writeJSON(w, http.StatusOK, map[string]any{
		"period": period,
		"summary": map[string]any{
			"total_revenue_eur":       totalRevenue,
			"total_costs_eur":         totalCosts,
			"gross_profit_eur":        grossProfit,
			"gross_margin_pct":        totalMarginPct,
			"units_sold":              n,
			"avg_margin_per_unit_eur": avgPerUnit,
			"avg_margin_pct":          avgMargin,
			"avg_days_in_stock":       avgDOM,
		},
		"vehicles": vehicles,
	})
}

// CRMGoalGet GET /api/v1/dealer/crm/goals/{period}
func (d *Deps) CRMGoalGet(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	period := r.PathValue("period")
	if entityULID == "" || period == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	ctx := r.Context()
	type goalRow struct {
		GoalULID         string  `json:"goal_ulid"`
		PeriodMonth      string  `json:"period_month"`
		TargetUnitsSold  int     `json:"target_units_sold"`
		TargetRevenueEUR float64 `json:"target_revenue_eur"`
		TargetMarginPct  float64 `json:"target_margin_pct"`
		TargetAvgDOM     int     `json:"target_avg_dom"`
		ActualUnitsSold  int     `json:"actual_units_sold"`
		ActualRevenueEUR float64 `json:"actual_revenue_eur"`
		ActualMarginPct  float64 `json:"actual_margin_pct"`
		ActualAvgDOM     int     `json:"actual_avg_dom"`
	}
	var g goalRow
	err := d.DB.QueryRow(ctx,
		`SELECT goal_ulid, period_month, target_units_sold, target_revenue_eur, target_margin_pct, target_avg_dom, actual_units_sold, actual_revenue_eur, actual_margin_pct, actual_avg_dom
		 FROM crm_goals WHERE entity_ulid=$1 AND period_month=$2`, entityULID, period).
		Scan(&g.GoalULID, &g.PeriodMonth, &g.TargetUnitsSold, &g.TargetRevenueEUR, &g.TargetMarginPct, &g.TargetAvgDOM, &g.ActualUnitsSold, &g.ActualRevenueEUR, &g.ActualMarginPct, &g.ActualAvgDOM)
	if err != nil {
		g.GoalULID = ulid.Make().String()
		g.PeriodMonth = period
		d.DB.Exec(ctx, `INSERT INTO crm_goals (goal_ulid, entity_ulid, period_month) VALUES ($1,$2,$3) ON CONFLICT (entity_ulid, period_month) DO NOTHING`, g.GoalULID, entityULID, period)
	}
	periodStart := period + "-01"
	d.DB.QueryRow(ctx, `
		SELECT count(*), coalesce(sum(sale_price_eur),0),
		       coalesce(avg(case when (purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur)>0 then (sale_price_eur-(purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur))/(purchase_price_eur+recon_cost_eur+transport_cost_eur+homologation_cost_eur+marketing_cost_eur+financing_cost_eur+other_cost_eur)*100 else null end),0),
		       coalesce(avg(CURRENT_DATE - stock_entry_date),0)
		FROM crm_vehicles WHERE entity_ulid=$1 AND lifecycle_status='SOLD'
		  AND sale_date >= $2::date AND sale_date < $2::date + INTERVAL '1 month'`,
		entityULID, periodStart).Scan(&g.ActualUnitsSold, &g.ActualRevenueEUR, &g.ActualMarginPct, &g.ActualAvgDOM)
	d.DB.Exec(ctx, //nolint
		`UPDATE crm_goals SET actual_units_sold=$1, actual_revenue_eur=$2, actual_margin_pct=$3, actual_avg_dom=$4, updated_at=now() WHERE entity_ulid=$5 AND period_month=$6`,
		g.ActualUnitsSold, g.ActualRevenueEUR, g.ActualMarginPct, g.ActualAvgDOM, entityULID, period)
	writeJSON(w, http.StatusOK, g)
}

// CRMGoalSet PUT /api/v1/dealer/crm/goals/{period}
func (d *Deps) CRMGoalSet(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	period := r.PathValue("period")
	if entityULID == "" || period == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	var req struct {
		TargetUnitsSold  int     `json:"target_units_sold"`
		TargetRevenueEUR float64 `json:"target_revenue_eur"`
		TargetMarginPct  float64 `json:"target_margin_pct"`
		TargetAvgDOM     int     `json:"target_avg_dom"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	id := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO crm_goals (goal_ulid, entity_ulid, period_month, target_units_sold, target_revenue_eur, target_margin_pct, target_avg_dom)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		ON CONFLICT (entity_ulid, period_month) DO UPDATE
		SET target_units_sold=$4, target_revenue_eur=$5, target_margin_pct=$6, target_avg_dom=$7, updated_at=now()`,
		id, entityULID, period, req.TargetUnitsSold, req.TargetRevenueEUR, req.TargetMarginPct, req.TargetAvgDOM)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "saved", "period": period})
}

// ── Helpers ───────────────────────────────────────────────────────────────────

