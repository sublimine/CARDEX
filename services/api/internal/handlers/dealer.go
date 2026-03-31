package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"
	"github.com/redis/go-redis/v9"
)

// InventoryList GET /api/v1/dealer/inventory
func (d *Deps) InventoryList(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())
	if dealerULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "dealer context missing")
		return
	}

	q := r.URL.Query()
	status := q.Get("status")
	page := parseInt(q.Get("page"), 1)
	perPage := parseInt(q.Get("per_page"), 50)
	if perPage > 200 {
		perPage = 200
	}

	args := []any{dealerULID}
	filter := ""
	if status != "" {
		filter = "AND listing_status = $2"
		args = append(args, status)
	}
	args = append(args, perPage, (page-1)*perPage)
	offsetIdx := len(args) - 1
	limitIdx := len(args) - 2

	rows, err := d.DB.Query(r.Context(),
		"SELECT inventory_ulid, vin, make, model, variant, year, mileage_km, "+
			"fuel_type, transmission, color, price_eur, listing_status, "+
			"photo_urls, platform_ids, marketing_score, created_at, updated_at "+
			"FROM dealer_inventory "+
			"WHERE dealer_ulid = $1 "+filter+
			" ORDER BY created_at DESC LIMIT $"+strconv.Itoa(limitIdx+1)+" OFFSET $"+strconv.Itoa(offsetIdx+1),
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type item struct {
		ULID         string            `json:"inventory_ulid"`
		VIN          *string           `json:"vin,omitempty"`
		Make         string            `json:"make"`
		Model        string            `json:"model"`
		Variant      *string           `json:"variant,omitempty"`
		Year         int               `json:"year"`
		MileageKM    int               `json:"mileage_km"`
		FuelType     *string           `json:"fuel_type,omitempty"`
		Transmission *string           `json:"transmission,omitempty"`
		Color        *string           `json:"color,omitempty"`
		PriceEUR     float64           `json:"price_eur"`
		Status       string            `json:"listing_status"`
		PhotoURLs    []string          `json:"photo_urls"`
		PlatformIDs  map[string]string `json:"platform_ids"`
		MarketScore  *int              `json:"marketing_score,omitempty"`
		CreatedAt    time.Time         `json:"created_at"`
		UpdatedAt    time.Time         `json:"updated_at"`
	}

	var items []item
	for rows.Next() {
		var it item
		var platformIDsJSON []byte
		if err := rows.Scan(
			&it.ULID, &it.VIN, &it.Make, &it.Model, &it.Variant,
			&it.Year, &it.MileageKM, &it.FuelType, &it.Transmission,
			&it.Color, &it.PriceEUR, &it.Status,
			&it.PhotoURLs, &platformIDsJSON, &it.MarketScore,
			&it.CreatedAt, &it.UpdatedAt,
		); err != nil {
			continue
		}
		if platformIDsJSON != nil {
			json.Unmarshal(platformIDsJSON, &it.PlatformIDs)
		}
		items = append(items, it)
	}
	if items == nil {
		items = []item{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "page": page})
}

// InventoryCreate POST /api/v1/dealer/inventory
func (d *Deps) InventoryCreate(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())

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
		PriceEUR     float64  `json:"price_eur"`
		PhotoURLs    []string `json:"photo_urls"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if body.Make == "" || body.Model == "" || body.Year == 0 {
		writeError(w, http.StatusBadRequest, "missing_fields", "make, model, year are required")
		return
	}

	inventoryULID := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO dealer_inventory (
			inventory_ulid, dealer_ulid, vin, make, model, variant,
			year, mileage_km, fuel_type, transmission, color,
			price_eur, photo_urls, listing_status
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'DRAFT')
	`,
		inventoryULID, dealerULID, body.VIN, body.Make, body.Model, body.Variant,
		body.Year, body.MileageKM, body.FuelType, body.Transmission, body.Color,
		body.PriceEUR, body.PhotoURLs,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"inventory_ulid": inventoryULID})
}

// InventoryUpdate PUT /api/v1/dealer/inventory/{ulid}
func (d *Deps) InventoryUpdate(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())
	inventoryULID := r.PathValue("ulid")

	var body struct {
		PriceEUR      *float64 `json:"price_eur"`
		MileageKM     *int     `json:"mileage_km"`
		ListingStatus *string  `json:"listing_status"`
		PhotoURLs     []string `json:"photo_urls"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	tag, err := d.DB.Exec(r.Context(), `
		UPDATE dealer_inventory SET
			price_eur      = COALESCE($3, price_eur),
			mileage_km     = COALESCE($4, mileage_km),
			listing_status = COALESCE($5, listing_status),
			photo_urls     = COALESCE($6, photo_urls),
			updated_at     = NOW()
		WHERE inventory_ulid = $1 AND dealer_ulid = $2
	`, inventoryULID, dealerULID, body.PriceEUR, body.MileageKM, body.ListingStatus, body.PhotoURLs)
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
	dealerULID := middleware.GetDealerULID(r.Context())
	inventoryULID := r.PathValue("ulid")
	d.DB.Exec(r.Context(),
		"UPDATE dealer_inventory SET listing_status = 'REMOVED', updated_at = NOW() WHERE inventory_ulid = $1 AND dealer_ulid = $2",
		inventoryULID, dealerULID,
	)
	writeJSON(w, http.StatusOK, map[string]string{"status": "removed"})
}

// InventoryImportURL POST /api/v1/dealer/inventory/import-url
func (d *Deps) InventoryImportURL(w http.ResponseWriter, r *http.Request) {
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
			"dealer_ulid":  middleware.GetDealerULID(r.Context()),
			"requested_at": time.Now().UTC().Format(time.RFC3339),
		},
	})
	writeJSON(w, http.StatusAccepted, map[string]string{
		"status":  "queued",
		"message": "Import queued. Your inventory will be pre-filled within 60 seconds.",
	})
}

// PublishJob POST /api/v1/dealer/publish
func (d *Deps) PublishJob(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())

	var body struct {
		InventoryULID string   `json:"inventory_ulid"`
		Platforms     []string `json:"platforms"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	jobULID := ulid.Make().String()
	for _, platform := range body.Platforms {
		rowULID := ulid.Make().String()
		d.DB.Exec(r.Context(), `
			INSERT INTO publish_jobs (job_ulid, inventory_ulid, dealer_ulid, platform, status)
			VALUES ($1, $2, $3, $4, 'PENDING')
		`, rowULID, body.InventoryULID, dealerULID, platform)
		d.Redis.XAdd(r.Context(), &redis.XAddArgs{
			Stream: "stream:publish_jobs",
			Values: map[string]any{
				"job_ulid":       jobULID,
				"row_ulid":       rowULID,
				"inventory_ulid": body.InventoryULID,
				"dealer_ulid":    dealerULID,
				"platform":       platform,
			},
		})
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_ulid": jobULID, "status": "queued"})
}

// PublishJobStatus GET /api/v1/dealer/publish/{job_id}
func (d *Deps) PublishJobStatus(w http.ResponseWriter, r *http.Request) {
	jobULID := r.PathValue("job_id")
	rows, err := d.DB.Query(r.Context(),
		"SELECT platform, status, external_id, error_message, updated_at FROM publish_jobs WHERE job_ulid = $1",
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
		UpdatedAt  string  `json:"updated_at"`
	}
	var statuses []jobStatus
	for rows.Next() {
		var s jobStatus
		var ts time.Time
		rows.Scan(&s.Platform, &s.Status, &s.ExternalID, &s.Error, &ts)
		s.UpdatedAt = ts.Format(time.RFC3339)
		statuses = append(statuses, s)
	}
	if statuses == nil {
		statuses = []jobStatus{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"job_ulid": jobULID, "platforms": statuses})
}

// LeadsList GET /api/v1/dealer/leads
func (d *Deps) LeadsList(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())
	status := r.URL.Query().Get("status")

	args := []any{dealerULID}
	filter := ""
	if status != "" {
		filter = "AND status = $2"
		args = append(args, status)
	}

	rows, err := d.DB.Query(r.Context(),
		"SELECT lead_ulid, inventory_ulid, contact_name, contact_email, message, status, created_at "+
			"FROM leads WHERE dealer_ulid = $1 "+filter+" ORDER BY created_at DESC LIMIT 200",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type lead struct {
		ULID          string  `json:"lead_ulid"`
		InventoryULID *string `json:"inventory_ulid,omitempty"`
		Name          string  `json:"contact_name"`
		Email         string  `json:"contact_email"`
		Message       *string `json:"message,omitempty"`
		Status        string  `json:"status"`
		CreatedAt     string  `json:"created_at"`
	}
	var leads []lead
	for rows.Next() {
		var l lead
		var ts time.Time
		rows.Scan(&l.ULID, &l.InventoryULID, &l.Name, &l.Email, &l.Message, &l.Status, &ts)
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
		DealerULID    string  `json:"dealer_ulid"`
		InventoryULID *string `json:"inventory_ulid"`
		Name          string  `json:"contact_name"`
		Email         string  `json:"contact_email"`
		Phone         *string `json:"contact_phone"`
		Message       *string `json:"message"`
		Channel       string  `json:"channel"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if body.DealerULID == "" || body.Name == "" || body.Email == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "dealer_ulid, contact_name, contact_email required")
		return
	}
	if body.Channel == "" {
		body.Channel = "CARDEX_WEB"
	}

	leadULID := ulid.Make().String()
	_, err := d.DB.Exec(r.Context(), `
		INSERT INTO leads (lead_ulid, dealer_ulid, inventory_ulid, contact_name, contact_email, contact_phone, message, channel, status)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'NEW')
	`, leadULID, body.DealerULID, body.InventoryULID, body.Name, body.Email, body.Phone, body.Message, body.Channel)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	d.Redis.XAdd(r.Context(), &redis.XAddArgs{
		Stream: "stream:lead_events",
		Values: map[string]any{
			"lead_ulid":   leadULID,
			"dealer_ulid": body.DealerULID,
			"channel":     body.Channel,
		},
	})
	writeJSON(w, http.StatusCreated, map[string]string{"lead_ulid": leadULID})
}

// LeadStatusUpdate PUT /api/v1/dealer/leads/{id}/status
func (d *Deps) LeadStatusUpdate(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())
	leadULID := r.PathValue("id")

	var body struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	valid := map[string]bool{
		"NEW": true, "CONTACTED": true, "VISIT_SCHEDULED": true,
		"NEGOTIATING": true, "SOLD": true, "LOST": true,
	}
	if !valid[body.Status] {
		writeError(w, http.StatusBadRequest, "invalid_status", "invalid status value")
		return
	}
	tag, err := d.DB.Exec(r.Context(),
		"UPDATE leads SET status = $1, updated_at = NOW() WHERE lead_ulid = $2 AND dealer_ulid = $3",
		body.Status, leadULID, dealerULID,
	)
	if err != nil || tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "lead not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": body.Status})
}

// PricingIntelligence GET /api/v1/dealer/pricing/{ulid}
func (d *Deps) PricingIntelligence(w http.ResponseWriter, r *http.Request) {
	inventoryULID := r.PathValue("ulid")

	var make_, model, country string
	var year, mileage int
	var priceEUR float64
	err := d.DB.QueryRow(r.Context(), `
		SELECT di.make, di.model, di.year, di.mileage_km, di.price_eur, de.country
		FROM dealer_inventory di
		JOIN dealers de ON di.dealer_ulid = de.dealer_ulid
		WHERE di.inventory_ulid = $1
	`, inventoryULID).Scan(&make_, &model, &year, &mileage, &priceEUR, &country)
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
		"inventory_ulid":  inventoryULID,
		"your_price_eur":  priceEUR,
		"market_p25":      p25,
		"market_median":   median,
		"market_p75":      p75,
		"avg_dom_days":    avgDOM,
		"market_sample":   sampleSize,
		"market_position": marketPosition,
		"country":         country,
	})
}

// MarketingAudit GET /api/v1/dealer/audit
func (d *Deps) MarketingAudit(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())

	var auditULID string
	var overallScore int
	var photoScore, descScore, pricingScore, responseScore *int
	var recommendations *string
	var ts time.Time

	err := d.DB.QueryRow(r.Context(), `
		SELECT audit_ulid, overall_score, photo_score, description_score,
		       pricing_score, response_time_score, recommendations, created_at
		FROM marketing_audits
		WHERE dealer_ulid = $1 ORDER BY created_at DESC LIMIT 1
	`, dealerULID).Scan(
		&auditULID, &overallScore, &photoScore, &descScore,
		&pricingScore, &responseScore, &recommendations, &ts,
	)
	if err != nil {
		writeError(w, http.StatusNotFound, "no_audit", "no audit available — trigger one via POST /audit/trigger")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"audit_ulid":         auditULID,
		"overall_score":      overallScore,
		"photo_score":        photoScore,
		"description_score":  descScore,
		"pricing_score":      pricingScore,
		"response_time_score": responseScore,
		"recommendations":    recommendations,
		"created_at":         ts.Format(time.RFC3339),
	})
}

// TriggerMarketingAudit POST /api/v1/dealer/audit/trigger
func (d *Deps) TriggerMarketingAudit(w http.ResponseWriter, r *http.Request) {
	dealerULID := middleware.GetDealerULID(r.Context())
	d.Redis.XAdd(r.Context(), &redis.XAddArgs{
		Stream: "stream:audit_jobs",
		Values: map[string]any{"dealer_ulid": dealerULID},
	})
	writeJSON(w, http.StatusAccepted, map[string]string{
		"status":  "queued",
		"message": "Marketing audit started. Results available in ~5 minutes.",
	})
}

// NLCCalculation GET /api/v1/dealer/nlc/{ulid}
func (d *Deps) NLCCalculation(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
}

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

// DealerRegister POST /api/v1/auth/register
func (d *Deps) DealerRegister(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
}

// DealerLogin POST /api/v1/auth/login
func (d *Deps) DealerLogin(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
}

// TokenRefresh POST /api/v1/auth/refresh
func (d *Deps) TokenRefresh(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
}
