package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cardex/alpha/pkg/nlc"
	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"
	"github.com/redis/go-redis/v9"
)

// ──────────────────────────────────────────────────────────────────────────────
// INVENTORY
// ──────────────────────────────────────────────────────────────────────────────

// InventoryList GET /api/v1/dealer/inventory
func (d *Deps) InventoryList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "dealer entity context missing")
		return
	}

	q := r.URL.Query()
	status := q.Get("status")
	page := parseInt(q.Get("page"), 1)
	perPage := parseInt(q.Get("per_page"), 50)
	if perPage > 200 {
		perPage = 200
	}

	args := []any{entityULID}
	filter := ""
	if status != "" {
		filter = "AND status = $2"
		args = append(args, status)
	}
	args = append(args, perPage, (page-1)*perPage)
	limitIdx := len(args) - 1
	offsetIdx := len(args)

	rows, err := d.DB.Query(r.Context(),
		"SELECT item_ulid, vin, make, model, variant, year, mileage_km, "+
			"fuel_type, transmission, color, asking_price_eur, status, "+
			"photo_urls, marketing_score, created_at, updated_at "+
			"FROM dealer_inventory "+
			"WHERE entity_ulid = $1 "+filter+
			" ORDER BY created_at DESC LIMIT $"+strconv.Itoa(limitIdx)+" OFFSET $"+strconv.Itoa(offsetIdx),
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type item struct {
		ULID         string   `json:"item_ulid"`
		VIN          *string  `json:"vin,omitempty"`
		Make         string   `json:"make"`
		Model        string   `json:"model"`
		Variant      *string  `json:"variant,omitempty"`
		Year         int      `json:"year"`
		MileageKM    int      `json:"mileage_km"`
		FuelType     *string  `json:"fuel_type,omitempty"`
		Transmission *string  `json:"transmission,omitempty"`
		Color        *string  `json:"color,omitempty"`
		PriceEUR     float64  `json:"asking_price_eur"`
		Status       string   `json:"status"`
		PhotoURLs    []string `json:"photo_urls"`
		MarketScore  *float64 `json:"marketing_score,omitempty"`
		CreatedAt    string   `json:"created_at"`
		UpdatedAt    string   `json:"updated_at"`
	}

	var items []item
	for rows.Next() {
		var it item
		var createdAt, updatedAt time.Time
		if err := rows.Scan(
			&it.ULID, &it.VIN, &it.Make, &it.Model, &it.Variant,
			&it.Year, &it.MileageKM, &it.FuelType, &it.Transmission,
			&it.Color, &it.PriceEUR, &it.Status,
			&it.PhotoURLs, &it.MarketScore,
			&createdAt, &updatedAt,
		); err != nil {
			continue
		}
		it.CreatedAt = createdAt.Format(time.RFC3339)
		it.UpdatedAt = updatedAt.Format(time.RFC3339)
		items = append(items, it)
	}
	if items == nil {
		items = []item{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "page": page})
}

// InventoryCreate POST /api/v1/dealer/inventory
func (d *Deps) InventoryCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "dealer entity context missing")
		return
	}

	var body struct {
		VIN          *string  `json:"vin"`
		Make         string   `json:"make"`
		Model        string   `json:"model"`
		Variant      *string  `json:"variant"`
		Year         int      `json:"year"`
		MileageKM    int      `json:"mileage_km"`
		FuelType     *string  `json:"fuel_type"`
		Transmission *string  `json:"transmission"`
		Color        *string  `json:"color"`
		PriceEUR     float64  `json:"asking_price_eur"`
		PhotoURLs    []string `json:"photo_urls"`
		Description  *string  `json:"description"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if body.Make == "" || body.Model == "" || body.Year == 0 || body.PriceEUR <= 0 {
		writeError(w, http.StatusBadRequest, "missing_fields", "make, model, year, asking_price_eur are required")
		return
	}

	itemULID := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO dealer_inventory (
			item_ulid, entity_ulid, vin, make, model, variant,
			year, mileage_km, fuel_type, transmission, color,
			asking_price_eur, photo_urls, description, status
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'AVAILABLE')
	`,
		itemULID, entityULID, body.VIN, body.Make, body.Model, body.Variant,
		body.Year, body.MileageKM, body.FuelType, body.Transmission, body.Color,
		body.PriceEUR, body.PhotoURLs, body.Description,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"item_ulid": itemULID})
}

// InventoryUpdate PUT /api/v1/dealer/inventory/{ulid}
func (d *Deps) InventoryUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	itemULID := r.PathValue("ulid")

	var body struct {
		PriceEUR  *float64 `json:"asking_price_eur"`
		MileageKM *int     `json:"mileage_km"`
		Status    *string  `json:"status"`
		PhotoURLs []string `json:"photo_urls"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	tag, err := d.DB.Exec(r.Context(), `
		UPDATE dealer_inventory SET
			asking_price_eur = COALESCE($3, asking_price_eur),
			mileage_km       = COALESCE($4, mileage_km),
			status           = COALESCE($5, status),
			photo_urls       = COALESCE($6, photo_urls),
			updated_at       = NOW()
		WHERE item_ulid = $1 AND entity_ulid = $2
	`, itemULID, entityULID, body.PriceEUR, body.MileageKM, body.Status, body.PhotoURLs)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "inventory item not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// InventoryDelete DELETE /api/v1/dealer/inventory/{ulid}
func (d *Deps) InventoryDelete(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	itemULID := r.PathValue("ulid")
	d.DB.Exec(r.Context(),
		"UPDATE dealer_inventory SET status = 'DELISTED', updated_at = NOW() WHERE item_ulid = $1 AND entity_ulid = $2",
		itemULID, entityULID,
	)
	writeJSON(w, http.StatusOK, map[string]string{"status": "delisted"})
}

// InventoryImportURL POST /api/v1/dealer/inventory/import-url
func (d *Deps) InventoryImportURL(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	var body struct {
		URL string `json:"url"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.URL == "" {
		writeError(w, http.StatusBadRequest, "invalid_body", "url is required")
		return
	}
	d.Redis.XAdd(r.Context(), &redis.XAddArgs{
		Stream: "stream:import_url_jobs",
		Values: map[string]any{
			"url":          body.URL,
			"entity_ulid":  entityULID,
			"requested_at": time.Now().UTC().Format(time.RFC3339),
		},
	})
	writeJSON(w, http.StatusAccepted, map[string]string{
		"status":  "queued",
		"message": "Import queued. Your inventory will be pre-filled within 60 seconds.",
	})
}

// ──────────────────────────────────────────────────────────────────────────────
// MULTIPOSTING
// ──────────────────────────────────────────────────────────────────────────────

// PublishJob POST /api/v1/dealer/publish
func (d *Deps) PublishJob(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())

	var body struct {
		ItemULID  string   `json:"item_ulid"`
		Platforms []string `json:"platforms"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if body.ItemULID == "" || len(body.Platforms) == 0 {
		writeError(w, http.StatusBadRequest, "missing_fields", "item_ulid and platforms are required")
		return
	}

	jobULID := ulid.Make().String()
	for _, platform := range body.Platforms {
		rowULID := ulid.Make().String()
		d.DB.Exec(r.Context(), `
			INSERT INTO publish_jobs (job_ulid, item_ulid, entity_ulid, platform, status)
			VALUES ($1, $2, $3, $4, 'PENDING')
		`, rowULID, body.ItemULID, entityULID, platform)
		d.Redis.XAdd(r.Context(), &redis.XAddArgs{
			Stream: "stream:publish_jobs",
			Values: map[string]any{
				"job_ulid":    jobULID,
				"row_ulid":    rowULID,
				"item_ulid":   body.ItemULID,
				"entity_ulid": entityULID,
				"platform":    platform,
			},
		})
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_ulid": jobULID, "status": "queued"})
}

// PublishJobStatus GET /api/v1/dealer/publish/{job_id}
func (d *Deps) PublishJobStatus(w http.ResponseWriter, r *http.Request) {
	jobULID := r.PathValue("job_id")
	rows, err := d.DB.Query(r.Context(),
		"SELECT platform, status, external_id, error_message, created_at FROM publish_jobs WHERE job_ulid = $1",
		jobULID,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type jobStatus struct {
		Platform   string  `json:"platform"`
		Status     string  `json:"status"`
		ExternalID *string `json:"external_id,omitempty"`
		Error      *string `json:"error,omitempty"`
		CreatedAt  string  `json:"created_at"`
	}
	var statuses []jobStatus
	for rows.Next() {
		var s jobStatus
		var ts time.Time
		rows.Scan(&s.Platform, &s.Status, &s.ExternalID, &s.Error, &ts)
		s.CreatedAt = ts.Format(time.RFC3339)
		statuses = append(statuses, s)
	}
	if statuses == nil {
		statuses = []jobStatus{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"job_ulid": jobULID, "platforms": statuses})
}

// ──────────────────────────────────────────────────────────────────────────────
// LEADS / CRM
// ──────────────────────────────────────────────────────────────────────────────

// LeadsList GET /api/v1/dealer/leads
func (d *Deps) LeadsList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	status := r.URL.Query().Get("status")

	args := []any{entityULID}
	filter := ""
	if status != "" {
		filter = "AND status = $2"
		args = append(args, status)
	}

	rows, err := d.DB.Query(r.Context(),
		"SELECT lead_ulid, item_ulid, contact_name, contact_email, message, status, created_at "+
			"FROM leads WHERE entity_ulid = $1 "+filter+" ORDER BY created_at DESC LIMIT 200",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type lead struct {
		ULID      string  `json:"lead_ulid"`
		ItemULID  *string `json:"item_ulid,omitempty"`
		Name      *string `json:"contact_name,omitempty"`
		Email     *string `json:"contact_email,omitempty"`
		Message   *string `json:"message,omitempty"`
		Status    string  `json:"status"`
		CreatedAt string  `json:"created_at"`
	}
	var leads []lead
	for rows.Next() {
		var l lead
		var ts time.Time
		rows.Scan(&l.ULID, &l.ItemULID, &l.Name, &l.Email, &l.Message, &l.Status, &ts)
		l.CreatedAt = ts.Format(time.RFC3339)
		leads = append(leads, l)
	}
	if leads == nil {
		leads = []lead{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"leads": leads})
}

// LeadCreate POST /api/v1/dealer/leads (public — buyer contacts dealer)
func (d *Deps) LeadCreate(w http.ResponseWriter, r *http.Request) {
	var body struct {
		EntityULID string  `json:"entity_ulid"`
		ItemULID   *string `json:"item_ulid"`
		VehicleULID *string `json:"vehicle_ulid"`
		Name       string  `json:"contact_name"`
		Email      string  `json:"contact_email"`
		Phone      *string `json:"contact_phone"`
		Message    *string `json:"message"`
		Platform   string  `json:"source_platform"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if body.EntityULID == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "entity_ulid is required")
		return
	}
	if body.Platform == "" {
		body.Platform = "CARDEX_WEB"
	}

	leadULID := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO leads (lead_ulid, entity_ulid, item_ulid, vehicle_ulid, contact_name, contact_email, contact_phone, message, source_platform, status)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'NEW')
	`, leadULID, body.EntityULID, body.ItemULID, body.VehicleULID, body.Name, body.Email, body.Phone, body.Message, body.Platform)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	d.Redis.XAdd(r.Context(), &redis.XAddArgs{
		Stream: "stream:lead_events",
		Values: map[string]any{
			"lead_ulid":   leadULID,
			"entity_ulid": body.EntityULID,
			"platform":    body.Platform,
		},
	})
	writeJSON(w, http.StatusCreated, map[string]string{"lead_ulid": leadULID})
}

// LeadStatusUpdate PUT /api/v1/dealer/leads/{id}/status
func (d *Deps) LeadStatusUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	leadULID := r.PathValue("id")

	var body struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	valid := map[string]bool{
		"NEW": true, "CONTACTED": true, "NEGOTIATING": true, "SOLD": true, "LOST": true,
	}
	if !valid[body.Status] {
		writeError(w, http.StatusBadRequest, "invalid_status", "valid values: NEW, CONTACTED, NEGOTIATING, SOLD, LOST")
		return
	}
	tag, err := d.DB.Exec(r.Context(),
		"UPDATE leads SET status = $1, updated_at = NOW() WHERE lead_ulid = $2 AND entity_ulid = $3",
		body.Status, leadULID, entityULID,
	)
	if err != nil || tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "lead not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": body.Status})
}

// ──────────────────────────────────────────────────────────────────────────────
// PRICING INTELLIGENCE & ANALYTICS
// ──────────────────────────────────────────────────────────────────────────────

// PricingIntelligence GET /api/v1/dealer/pricing/{ulid}
func (d *Deps) PricingIntelligence(w http.ResponseWriter, r *http.Request) {
	itemULID := r.PathValue("ulid")
	entityULID := middleware.GetEntityULID(r.Context())

	var make_, model, country string
	var year, mileage int
	var priceEUR float64
	err := d.DB.QueryRow(r.Context(), `
		SELECT di.make, di.model, di.year, di.mileage_km, di.asking_price_eur, e.country_code
		FROM dealer_inventory di
		JOIN entities e ON di.entity_ulid = e.entity_ulid
		WHERE di.item_ulid = $1 AND di.entity_ulid = $2
	`, itemULID, entityULID).Scan(&make_, &model, &year, &mileage, &priceEUR, &country)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "inventory item not found")
		return
	}

	var p25, median, p75, avgDOM float64
	var sampleSize uint64
	d.CH.QueryRow(r.Context(), `
		SELECT p25, median, p75, median_dom, sample_size
		FROM cardex.price_index
		WHERE make = ? AND model = ? AND country = ?
		  AND snapshot_date >= today() - 7
		ORDER BY snapshot_date DESC
		LIMIT 1
	`, make_, model, country).Scan(&p25, &median, &p75, &avgDOM, &sampleSize)

	marketPosition := "UNKNOWN"
	if median > 0 {
		pctDiff := (priceEUR - median) / median * 100
		switch {
		case pctDiff < -15:
			marketPosition = "GREAT_DEAL"
		case pctDiff < -5:
			marketPosition = "GOOD_DEAL"
		case pctDiff <= 5:
			marketPosition = "FAIR"
		case pctDiff <= 15:
			marketPosition = "EXPENSIVE"
		default:
			marketPosition = "OVERPRICED"
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"item_ulid":      itemULID,
		"your_price_eur": priceEUR,
		"market_p25":     p25,
		"market_median":  median,
		"market_p75":     p75,
		"avg_dom_days":   avgDOM,
		"market_sample":  sampleSize,
		"market_position": marketPosition,
		"country":        country,
	})
}

// MarketingAudit GET /api/v1/dealer/audit
func (d *Deps) MarketingAudit(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())

	var auditULID string
	var overallScore, photoScore, descScore, priceScore float64
	var recommendationsJSON *string
	var ts time.Time

	err := d.DB.QueryRow(r.Context(), `
		SELECT audit_ulid, overall_score, photo_score, description_score,
		       price_score, recommendations, generated_at
		FROM marketing_audits
		WHERE entity_ulid = $1 ORDER BY generated_at DESC LIMIT 1
	`, entityULID).Scan(
		&auditULID, &overallScore, &photoScore, &descScore,
		&priceScore, &recommendationsJSON, &ts,
	)
	if err != nil {
		writeError(w, http.StatusNotFound, "no_audit", "no audit available — trigger one via POST /audit/trigger")
		return
	}

	// recommendations is JSONB; decode to string slice for API consumers
	var recs []string
	if recommendationsJSON != nil {
		json.Unmarshal([]byte(*recommendationsJSON), &recs)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"audit_ulid":        auditULID,
		"overall_score":     int(overallScore * 100), // store 0-1, expose 0-100
		"photo_score":       int(photoScore * 100),
		"description_score": int(descScore * 100),
		"pricing_score":     int(priceScore * 100),
		"recommendations":   recs,
		"created_at":        ts.Format(time.RFC3339),
	})
}

// TriggerMarketingAudit POST /api/v1/dealer/audit/trigger
func (d *Deps) TriggerMarketingAudit(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	d.Redis.XAdd(r.Context(), &redis.XAddArgs{
		Stream: "stream:audit_jobs",
		Values: map[string]any{"entity_ulid": entityULID},
	})
	writeJSON(w, http.StatusAccepted, map[string]string{
		"status":  "queued",
		"message": "Marketing audit started. Results available in ~5 minutes.",
	})
}

// ──────────────────────────────────────────────────────────────────────────────
// NLC (Net Landed Cost)
// ──────────────────────────────────────────────────────────────────────────────

// NLCCalculation GET /api/v1/dealer/nlc/{ulid}?target_country=ES
func (d *Deps) NLCCalculation(w http.ResponseWriter, r *http.Request) {
	if d.NLCCalc == nil {
		writeError(w, http.StatusServiceUnavailable, "nlc_unavailable", "NLC engine not initialised")
		return
	}

	itemULID := r.PathValue("ulid")
	entityULID := middleware.GetEntityULID(r.Context())
	targetCountry := strings.ToUpper(r.URL.Query().Get("target_country"))

	var make_, model, originCountry string
	var year, co2GKM int
	var priceEUR float64

	err := d.DB.QueryRow(r.Context(), `
		SELECT di.make, di.model, di.year,
		       COALESCE(e.country_code, 'DE'),
		       COALESCE((SELECT gross_physical_cost_eur FROM vehicles WHERE vin = di.vin LIMIT 1), di.asking_price_eur, 0)
		FROM dealer_inventory di
		JOIN entities e ON di.entity_ulid = e.entity_ulid
		WHERE di.item_ulid = $1 AND di.entity_ulid = $2
	`, itemULID, entityULID).Scan(&make_, &model, &year, &originCountry, &priceEUR)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "inventory item not found")
		return
	}

	// Best-effort CO2 lookup from historical vehicles data
	d.DB.QueryRow(r.Context(), `
		SELECT COALESCE(co2_gkm, 0) FROM vehicles
		WHERE make = $1 AND model = $2 AND year = $3
		ORDER BY last_updated_at DESC LIMIT 1
	`, make_, model, year).Scan(&co2GKM)

	if targetCountry == "" {
		targetCountry = originCountry
	}

	now := time.Now()
	vehicleAgeYears := 0
	if year > 0 {
		vehicleAgeYears = now.Year() - year
		if vehicleAgeYears < 0 {
			vehicleAgeYears = 0
		}
	}

	result, err := d.NLCCalc.Compute(r.Context(), nlc.NLCInput{
		GrossPhysicalCostEUR: priceEUR,
		OriginCountry:        originCountry,
		TargetCountry:        targetCountry,
		CO2GKM:               co2GKM,
		VehicleAgeYears:      vehicleAgeYears,
		VehicleAgeMonths:     vehicleAgeYears * 12,
	})
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "nlc_error", err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"item_ulid":               itemULID,
		"gross_physical_cost_eur": priceEUR,
		"logistics_cost_eur":      result.LogisticsCostEUR,
		"tax_amount_eur":          result.TaxAmountEUR,
		"net_landed_cost_eur":     result.NetLandedCostEUR,
		"origin_country":          originCountry,
		"target_country":          targetCountry,
		"co2_gkm":                 co2GKM,
		"vehicle_age_years":       vehicleAgeYears,
	})
}

// ──────────────────────────────────────────────────────────────────────────────
// SDI Score
// ──────────────────────────────────────────────────────────────────────────────

// SDIScore GET /api/v1/dealer/sdi/{ulid}
func (d *Deps) SDIScore(w http.ResponseWriter, r *http.Request) {
	vehicleULID := r.PathValue("ulid")
	var priceDropCount int
	var priceEUR, lastPriceEUR float64
	var firstSeenAt time.Time

	err := d.DB.QueryRow(r.Context(),
		"SELECT price_drop_count, gross_physical_cost_eur, COALESCE(last_price_eur,0), first_seen_at FROM vehicles WHERE vehicle_ulid = $1",
		vehicleULID,
	).Scan(&priceDropCount, &priceEUR, &lastPriceEUR, &firstSeenAt)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "vehicle not found")
		return
	}

	dom := int(time.Since(firstSeenAt).Hours() / 24)
	score := 0
	var flags []string

	if priceDropCount >= 3 {
		score += 40
		flags = append(flags, "3+ price drops")
	} else if priceDropCount >= 1 {
		score += 20
		flags = append(flags, "price drop detected")
	}
	if dom > 60 {
		score += 30
		flags = append(flags, "60+ days on market")
	} else if dom > 30 {
		score += 15
		flags = append(flags, "30+ days on market")
	}
	if lastPriceEUR > 0 && priceEUR < lastPriceEUR*0.90 {
		score += 20
		flags = append(flags, ">10% last price cut")
	}

	label := "STABLE"
	switch {
	case score >= 70:
		label = "PANIC_SELLER"
	case score >= 40:
		label = "MOTIVATED_SELLER"
	case score >= 20:
		label = "NEGOTIABLE"
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"vehicle_ulid":      vehicleULID,
		"sdi_score":         score,
		"sdi_label":         label,
		"sdi_flags":         flags,
		"price_drop_count":  priceDropCount,
		"days_on_market":    dom,
		"current_price_eur": priceEUR,
		"last_price_eur":    lastPriceEUR,
	})
}

// DealerRegister, DealerLogin, TokenRefresh are implemented in auth.go
