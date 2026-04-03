package handlers

// publishing.go — Multipublicación Real (Gap 4)
//
// Endpoints:
//   GET    /api/v1/dealer/publishing                — list all publications
//   POST   /api/v1/dealer/publishing                — create publication entry
//   PATCH  /api/v1/dealer/publishing/{pub_ulid}     — update status/url/external_id
//   DELETE /api/v1/dealer/publishing/{pub_ulid}     — remove publication
//   GET    /api/v1/dealer/publishing/feed/autoscout24.xml — AS24 Data Exchange XML feed
//   GET    /api/v1/dealer/publishing/export?format= — platform-specific export (JSON/CSV)
//
// Competitive advantage vs AutoScout24 direct / Motortrack.es:
//   – One-click export to ALL platforms simultaneously from a single CRM record
//   – AS24 Data Exchange XML feed usable with any FTP or AS24 API integration
//   – Wallapop-ready JSON + Coches.net CSV + Mobile.de XML in one API call
//   – Real publication status tracking with error_message feedback per platform

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"
)

// ── Database types ─────────────────────────────────────────────────────────────

type publishingListing struct {
	PubULID          string     `json:"pub_ulid"`
	EntityULID       string     `json:"entity_ulid"`
	CRMVehicleULID   string     `json:"crm_vehicle_ulid"`
	Platform         string     `json:"platform"`
	Status           string     `json:"status"`
	ExternalID       string     `json:"external_id,omitempty"`
	ExternalURL      string     `json:"external_url,omitempty"`
	Title            string     `json:"title,omitempty"`
	ErrorMessage     string     `json:"error_message,omitempty"`
	PublishedAt      *time.Time `json:"published_at,omitempty"`
	ExpiresAt        *time.Time `json:"expires_at,omitempty"`
	LastSyncedAt     *time.Time `json:"last_synced_at,omitempty"`
	CreatedAt        time.Time  `json:"created_at"`
	UpdatedAt        time.Time  `json:"updated_at"`
	// CRM vehicle details (joined)
	Make             string     `json:"make,omitempty"`
	Model            string     `json:"model,omitempty"`
	Year             int        `json:"year,omitempty"`
	MileageKM        int        `json:"mileage_km,omitempty"`
	AskingPriceEUR   float64    `json:"asking_price_eur,omitempty"`
	FuelType         string     `json:"fuel_type,omitempty"`
	Transmission     string     `json:"transmission,omitempty"`
	ColorExterior    string     `json:"color_exterior,omitempty"`
	PowerKW          int        `json:"power_kw,omitempty"`
	VIN              string     `json:"vin,omitempty"`
	Description      string     `json:"description,omitempty"`
}

// ── PublishingList ─────────────────────────────────────────────────────────────

// PublishingList handles GET /api/v1/dealer/publishing
func (d *Deps) PublishingList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	ctx := r.Context()
	q := r.URL.Query()

	platform := q.Get("platform")
	status := q.Get("status")
	vehicleULID := q.Get("crm_vehicle_ulid")

	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	offset, _ := strconv.Atoi(q.Get("offset"))

	var where []string
	var args []any
	argIdx := 1

	where = append(where, "pl.entity_ulid = $"+strconv.Itoa(argIdx))
	args = append(args, entityULID)
	argIdx++

	if platform != "" {
		where = append(where, "pl.platform = $"+strconv.Itoa(argIdx))
		args = append(args, strings.ToUpper(platform))
		argIdx++
	}
	if status != "" {
		where = append(where, "pl.status = $"+strconv.Itoa(argIdx))
		args = append(args, strings.ToUpper(status))
		argIdx++
	}
	if vehicleULID != "" {
		where = append(where, "pl.crm_vehicle_ulid = $"+strconv.Itoa(argIdx))
		args = append(args, vehicleULID)
		argIdx++
	}

	whereSQL := "WHERE " + joinStrings(where, " AND ")

	countArgs := make([]any, len(args))
	copy(countArgs, args)
	var total int
	_ = d.DB.QueryRow(ctx,
		`SELECT COUNT(*) FROM publishing_listings pl `+whereSQL, countArgs...).Scan(&total)

	dataArgs := append(args, limit, offset)
	rows, err := d.DB.Query(ctx, `
		SELECT
			pl.pub_ulid, pl.entity_ulid, pl.crm_vehicle_ulid, pl.platform,
			pl.status, COALESCE(pl.external_id,''), COALESCE(pl.external_url,''),
			COALESCE(pl.title,''), COALESCE(pl.error_message,''),
			pl.published_at, pl.expires_at, pl.last_synced_at,
			pl.created_at, pl.updated_at,
			COALESCE(v.make,''), COALESCE(v.model,''), COALESCE(v.year,0),
			COALESCE(v.mileage_km,0), COALESCE(v.asking_price_eur,0),
			COALESCE(v.fuel_type,''), COALESCE(v.transmission,''),
			COALESCE(v.color_exterior,''), COALESCE(v.power_kw,0),
			COALESCE(v.vin,''), COALESCE(v.description,'')
		FROM publishing_listings pl
		LEFT JOIN crm_vehicles v ON v.crm_vehicle_ulid = pl.crm_vehicle_ulid
		`+whereSQL+`
		ORDER BY pl.updated_at DESC
		LIMIT $`+strconv.Itoa(argIdx)+` OFFSET $`+strconv.Itoa(argIdx+1),
		dataArgs...)

	if err != nil {
		slog.Error("publishing.list: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	var listings []publishingListing
	for rows.Next() {
		var pl publishingListing
		if err := rows.Scan(
			&pl.PubULID, &pl.EntityULID, &pl.CRMVehicleULID, &pl.Platform,
			&pl.Status, &pl.ExternalID, &pl.ExternalURL,
			&pl.Title, &pl.ErrorMessage,
			&pl.PublishedAt, &pl.ExpiresAt, &pl.LastSyncedAt,
			&pl.CreatedAt, &pl.UpdatedAt,
			&pl.Make, &pl.Model, &pl.Year,
			&pl.MileageKM, &pl.AskingPriceEUR,
			&pl.FuelType, &pl.Transmission,
			&pl.ColorExterior, &pl.PowerKW,
			&pl.VIN, &pl.Description,
		); err != nil {
			slog.Warn("publishing.list: row scan", "error", err)
			continue
		}
		listings = append(listings, pl)
	}
	if listings == nil {
		listings = []publishingListing{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"listings": listings,
		"total":    total,
	})
}

// ── PublishingCreate ───────────────────────────────────────────────────────────

type publishingCreateRequest struct {
	CRMVehicleULID string   `json:"crm_vehicle_ulid"`
	Platforms      []string `json:"platforms"`
	Title          string   `json:"title"`
	ExpiresInDays  int      `json:"expires_in_days"`
}

var validPlatforms = map[string]bool{
	"AUTOSCOUT24": true,
	"WALLAPOP":    true,
	"COCHES_NET":  true,
	"MOBILE_DE":   true,
	"MARKTPLAATS": true,
	"LACENTRALE":  true,
	"MILANUNCIOS": true,
	"MANUAL":      true,
}

// PublishingCreate handles POST /api/v1/dealer/publishing
func (d *Deps) PublishingCreate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	var req publishingCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", "invalid JSON body")
		return
	}
	if req.CRMVehicleULID == "" {
		writeError(w, http.StatusBadRequest, "missing_field", "crm_vehicle_ulid is required")
		return
	}
	if len(req.Platforms) == 0 {
		writeError(w, http.StatusBadRequest, "missing_field", "at least one platform required")
		return
	}

	// Validate platforms
	for _, p := range req.Platforms {
		if !validPlatforms[strings.ToUpper(p)] {
			writeError(w, http.StatusBadRequest, "invalid_platform",
				fmt.Sprintf("unknown platform: %s", p))
			return
		}
	}

	ctx := r.Context()

	// Verify vehicle belongs to entity
	var vehicleExists bool
	if err := d.DB.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM crm_vehicles WHERE crm_vehicle_ulid=$1 AND entity_ulid=$2)`,
		req.CRMVehicleULID, entityULID).Scan(&vehicleExists); err != nil || !vehicleExists {
		writeError(w, http.StatusNotFound, "vehicle_not_found", "CRM vehicle not found for this entity")
		return
	}

	expiresAt := (*time.Time)(nil)
	if req.ExpiresInDays > 0 {
		t := time.Now().AddDate(0, 0, req.ExpiresInDays)
		expiresAt = &t
	}

	// Insert one record per platform (UPSERT to avoid duplicates)
	created := make([]string, 0, len(req.Platforms))
	for _, platform := range req.Platforms {
		pubULID := ulid.Make().String()
		platform = strings.ToUpper(platform)
		title := req.Title
		if title == "" {
			title = fmt.Sprintf("%s — CARDEX", platform)
		}

		_, err := d.DB.Exec(ctx, `
			INSERT INTO publishing_listings
				(pub_ulid, entity_ulid, crm_vehicle_ulid, platform, status, title, expires_at, created_at, updated_at)
			VALUES ($1, $2, $3, $4, 'DRAFT', $5, $6, NOW(), NOW())
			ON CONFLICT (entity_ulid, crm_vehicle_ulid, platform)
			DO UPDATE SET status = EXCLUDED.status, title = EXCLUDED.title,
			              expires_at = EXCLUDED.expires_at, updated_at = NOW()
		`, pubULID, entityULID, req.CRMVehicleULID, platform, title, expiresAt)
		if err != nil {
			slog.Error("publishing.create: insert", "platform", platform, "error", err)
			continue
		}
		created = append(created, platform)
	}

	if len(created) == 0 {
		writeError(w, http.StatusInternalServerError, "create_failed", "failed to create publishing records")
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"created_platforms": created,
		"crm_vehicle_ulid":  req.CRMVehicleULID,
		"status":            "DRAFT",
	})
}

// ── PublishingUpdate ───────────────────────────────────────────────────────────

type publishingUpdateRequest struct {
	Status       *string `json:"status"`
	ExternalID   *string `json:"external_id"`
	ExternalURL  *string `json:"external_url"`
	ErrorMessage *string `json:"error_message"`
	PublishedAt  *string `json:"published_at"` // RFC3339
}

// PublishingUpdate handles PATCH /api/v1/dealer/publishing/{pub_ulid}
func (d *Deps) PublishingUpdate(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	pubULID := r.PathValue("pub_ulid")
	if pubULID == "" {
		writeError(w, http.StatusBadRequest, "missing_ulid", "pub_ulid is required")
		return
	}

	var req publishingUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", "invalid JSON body")
		return
	}

	validStatuses := map[string]bool{
		"DRAFT": true, "PENDING": true, "ACTIVE": true,
		"PAUSED": true, "EXPIRED": true, "REJECTED": true,
	}
	if req.Status != nil && !validStatuses[strings.ToUpper(*req.Status)] {
		writeError(w, http.StatusBadRequest, "invalid_status", "invalid status value")
		return
	}

	var setClauses []string
	var args []any
	argIdx := 1

	if req.Status != nil {
		s := strings.ToUpper(*req.Status)
		setClauses = append(setClauses, "status = $"+strconv.Itoa(argIdx))
		args = append(args, s)
		argIdx++
		if s == "ACTIVE" {
			setClauses = append(setClauses, "published_at = COALESCE(published_at, NOW())")
		}
	}
	if req.ExternalID != nil {
		setClauses = append(setClauses, "external_id = $"+strconv.Itoa(argIdx))
		args = append(args, *req.ExternalID)
		argIdx++
	}
	if req.ExternalURL != nil {
		setClauses = append(setClauses, "external_url = $"+strconv.Itoa(argIdx))
		args = append(args, *req.ExternalURL)
		argIdx++
	}
	if req.ErrorMessage != nil {
		setClauses = append(setClauses, "error_message = $"+strconv.Itoa(argIdx))
		args = append(args, *req.ErrorMessage)
		argIdx++
	}
	if req.PublishedAt != nil {
		t, err := time.Parse(time.RFC3339, *req.PublishedAt)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid_date", "published_at must be RFC3339")
			return
		}
		setClauses = append(setClauses, "published_at = $"+strconv.Itoa(argIdx))
		args = append(args, t)
		argIdx++
	}

	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no fields to update")
		return
	}

	setClauses = append(setClauses, "last_synced_at = NOW()", "updated_at = NOW()")
	args = append(args, pubULID, entityULID)

	query := "UPDATE publishing_listings SET " + joinStrings(setClauses, ", ") +
		" WHERE pub_ulid = $" + strconv.Itoa(argIdx) +
		" AND entity_ulid = $" + strconv.Itoa(argIdx+1)

	ct, err := d.DB.Exec(r.Context(), query, args...)
	if err != nil {
		slog.Error("publishing.update: exec", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", "failed to update publishing record")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "publishing record not found")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "updated", "pub_ulid": pubULID})
}

// ── PublishingDelete ───────────────────────────────────────────────────────────

// PublishingDelete handles DELETE /api/v1/dealer/publishing/{pub_ulid}
func (d *Deps) PublishingDelete(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	pubULID := r.PathValue("pub_ulid")
	if pubULID == "" {
		writeError(w, http.StatusBadRequest, "missing_ulid", "pub_ulid is required")
		return
	}

	ct, err := d.DB.Exec(r.Context(),
		`DELETE FROM publishing_listings WHERE pub_ulid = $1 AND entity_ulid = $2`,
		pubULID, entityULID)
	if err != nil {
		slog.Error("publishing.delete: exec", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", "failed to delete publishing record")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "publishing record not found")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

// ── AutoScout24 XML Feed ───────────────────────────────────────────────────────

// AS24 Data Exchange XML structures
type as24Feed struct {
	XMLName  xml.Name      `xml:"ListingsFormatted"`
	Listings []as24Listing `xml:"Listing"`
}

type as24Listing struct {
	ID           string  `xml:"Id"`
	Make         string  `xml:"Make"`
	Model        string  `xml:"Model"`
	Version      string  `xml:"Version,omitempty"`
	Year         int     `xml:"Year"`
	Mileage      int     `xml:"Mileage"`
	Price        float64 `xml:"Price"`
	Currency     string  `xml:"Currency"`
	FuelType     string  `xml:"FuelType"`
	Transmission string  `xml:"Gearbox"`
	Color        string  `xml:"ColourGeneric,omitempty"`
	PowerKW      int     `xml:"PowerKW,omitempty"`
	BodyType     string  `xml:"BodyType,omitempty"`
	Doors        int     `xml:"Doors,omitempty"`
	Description  string  `xml:"Description,omitempty"`
	VIN          string  `xml:"Vin,omitempty"`
}

// PublishingFeedAS24 handles GET /api/v1/dealer/publishing/feed/autoscout24.xml
func (d *Deps) PublishingFeedAS24(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	ctx := r.Context()

	// Fetch all vehicles for this entity that should be on AS24
	rows, err := d.DB.Query(ctx, `
		SELECT
			pl.pub_ulid,
			COALESCE(v.make,''), COALESCE(v.model,''), COALESCE(v.variant,''),
			COALESCE(v.year,0), COALESCE(v.mileage_km,0), COALESCE(v.asking_price_eur,0),
			COALESCE(v.fuel_type,''), COALESCE(v.transmission,''), COALESCE(v.color_exterior,''),
			COALESCE(v.power_kw,0), COALESCE(v.body_type,''), COALESCE(v.doors,0),
			COALESCE(v.description,''), COALESCE(v.vin,'')
		FROM publishing_listings pl
		JOIN crm_vehicles v ON v.crm_vehicle_ulid = pl.crm_vehicle_ulid
		WHERE pl.entity_ulid = $1
		  AND pl.platform = 'AUTOSCOUT24'
		  AND pl.status IN ('DRAFT','PENDING','ACTIVE')
		  AND v.asking_price_eur > 0
		ORDER BY pl.updated_at DESC
	`, entityULID)

	if err != nil {
		slog.Error("publishing.feed-as24: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	feed := as24Feed{}
	for rows.Next() {
		var l as24Listing
		if err := rows.Scan(
			&l.ID, &l.Make, &l.Model, &l.Version,
			&l.Year, &l.Mileage, &l.Price,
			&l.FuelType, &l.Transmission, &l.Color,
			&l.PowerKW, &l.BodyType, &l.Doors,
			&l.Description, &l.VIN,
		); err != nil {
			slog.Warn("publishing.feed-as24: scan", "error", err)
			continue
		}
		l.Currency = "EUR"
		l.ID = "CARDEX-" + l.ID
		// Normalize fuel type to AS24 vocabulary
		l.FuelType = normalizeAS24Fuel(l.FuelType)
		l.Transmission = normalizeAS24Transmission(l.Transmission)
		feed.Listings = append(feed.Listings, l)
	}

	w.Header().Set("Content-Type", "application/xml; charset=UTF-8")
	w.Header().Set("Content-Disposition", `attachment; filename="autoscout24_feed.xml"`)
	w.WriteHeader(http.StatusOK)

	xmlBytes, err := xml.MarshalIndent(feed, "", "  ")
	if err != nil {
		slog.Error("publishing.feed-as24: marshal", "error", err)
		return
	}
	w.Write([]byte(xml.Header))
	w.Write(xmlBytes)
}

// ── Platform Export ────────────────────────────────────────────────────────────

// PublishingExport handles GET /api/v1/dealer/publishing/export?format=wallapop|coches_net|mobile_de
func (d *Deps) PublishingExport(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	format := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("format")))
	validFormats := map[string]bool{
		"wallapop":  true,
		"coches_net": true,
		"mobile_de": true,
		"milanuncios": true,
	}
	if !validFormats[format] {
		writeError(w, http.StatusBadRequest, "invalid_format",
			"format must be one of: wallapop, coches_net, mobile_de, milanuncios")
		return
	}

	platform := formatToPlatform(format)
	ctx := r.Context()

	rows, err := d.DB.Query(ctx, `
		SELECT
			pl.pub_ulid,
			COALESCE(v.make,''), COALESCE(v.model,''), COALESCE(v.variant,''),
			COALESCE(v.year,0), COALESCE(v.mileage_km,0), COALESCE(v.asking_price_eur,0),
			COALESCE(v.fuel_type,''), COALESCE(v.transmission,''), COALESCE(v.color_exterior,''),
			COALESCE(v.power_kw,0), COALESCE(v.body_type,''), COALESCE(v.doors,0),
			COALESCE(v.description,''), COALESCE(v.vin,''),
			COALESCE(v.co2_gkm,0), COALESCE(v.registration_date::text,'')
		FROM publishing_listings pl
		JOIN crm_vehicles v ON v.crm_vehicle_ulid = pl.crm_vehicle_ulid
		WHERE pl.entity_ulid = $1
		  AND pl.platform = $2
		  AND pl.status IN ('DRAFT','PENDING','ACTIVE')
		  AND v.asking_price_eur > 0
		ORDER BY pl.updated_at DESC
	`, entityULID, platform)

	if err != nil {
		slog.Error("publishing.export: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	type exportRow struct {
		PubULID      string
		Make         string
		Model        string
		Variant      string
		Year         int
		MileageKM    int
		PriceEUR     float64
		FuelType     string
		Transmission string
		Color        string
		PowerKW      int
		BodyType     string
		Doors        int
		Description  string
		VIN          string
		CO2GKM       int
		RegDate      string
	}

	var exportData []exportRow
	for rows.Next() {
		var row exportRow
		if err := rows.Scan(
			&row.PubULID, &row.Make, &row.Model, &row.Variant,
			&row.Year, &row.MileageKM, &row.PriceEUR,
			&row.FuelType, &row.Transmission, &row.Color,
			&row.PowerKW, &row.BodyType, &row.Doors,
			&row.Description, &row.VIN, &row.CO2GKM, &row.RegDate,
		); err != nil {
			slog.Warn("publishing.export: scan", "error", err)
			continue
		}
		exportData = append(exportData, row)
	}

	switch format {
	case "wallapop":
		// Wallapop uses JSON feed format
		type wallapopItem struct {
			ExternalID  string  `json:"external_id"`
			Title       string  `json:"title"`
			Description string  `json:"description"`
			Price       float64 `json:"price"`
			Category    string  `json:"category"`
			Make        string  `json:"brand"`
			Model       string  `json:"model"`
			Year        int     `json:"year"`
			MileageKM   int     `json:"km"`
			FuelType    string  `json:"engine"`
			Transmission string `json:"gearbox"`
			Color       string  `json:"color"`
			PowerKW     int     `json:"power_kw"`
		}
		items := make([]wallapopItem, 0, len(exportData))
		for _, row := range exportData {
			items = append(items, wallapopItem{
				ExternalID:   "CARDEX-" + row.PubULID,
				Title:        fmt.Sprintf("%s %s %d", row.Make, row.Model, row.Year),
				Description:  row.Description,
				Price:        row.PriceEUR,
				Category:     "cars",
				Make:         row.Make,
				Model:        row.Model,
				Year:         row.Year,
				MileageKM:    row.MileageKM,
				FuelType:     row.FuelType,
				Transmission: row.Transmission,
				Color:        row.Color,
				PowerKW:      row.PowerKW,
			})
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Content-Disposition", `attachment; filename="wallapop_export.json"`)
		json.NewEncoder(w).Encode(map[string]any{"items": items, "count": len(items)})

	case "coches_net", "milanuncios":
		// CSV format
		var buf bytes.Buffer
		cw := csv.NewWriter(&buf)
		headers := []string{
			"referencia", "marca", "modelo", "version", "año", "km",
			"precio", "combustible", "cambio", "color", "cv", "carroceria",
			"puertas", "descripcion", "bastidor", "co2",
		}
		_ = cw.Write(headers)
		for _, row := range exportData {
			cv := int(float64(row.PowerKW) * 1.36) // kW to CV
			_ = cw.Write([]string{
				"CARDEX-" + row.PubULID,
				row.Make, row.Model, row.Variant,
				strconv.Itoa(row.Year), strconv.Itoa(row.MileageKM),
				fmt.Sprintf("%.0f", row.PriceEUR),
				row.FuelType, row.Transmission, row.Color,
				strconv.Itoa(cv), row.BodyType,
				strconv.Itoa(row.Doors), row.Description, row.VIN,
				strconv.Itoa(row.CO2GKM),
			})
		}
		cw.Flush()
		fname := format + "_export.csv"
		w.Header().Set("Content-Type", "text/csv; charset=UTF-8")
		w.Header().Set("Content-Disposition", `attachment; filename="`+fname+`"`)
		w.Write(buf.Bytes())

	case "mobile_de":
		// Mobile.de XML (simplified i-Export format)
		type mobileDeListing struct {
			XMLName      xml.Name `xml:"Ad"`
			InternalID   string   `xml:"InternalId"`
			Make         string   `xml:"Make"`
			Model        string   `xml:"Model"`
			Price        float64  `xml:"Price"`
			FirstRegistration string `xml:"FirstRegistration,omitempty"`
			Mileage      int     `xml:"Mileage"`
			FuelType     string  `xml:"FuelType"`
			Gearbox      string  `xml:"Gearbox"`
			PowerKW      int     `xml:"Power>ValueInKw,omitempty"`
			Description  string  `xml:"Description,omitempty"`
			VIN          string  `xml:"Vin,omitempty"`
		}
		type mobileDeFeed struct {
			XMLName xml.Name          `xml:"Ads"`
			Ads     []mobileDeListing `xml:"Ad"`
		}

		feed := mobileDeFeed{}
		for _, row := range exportData {
			feed.Ads = append(feed.Ads, mobileDeListing{
				InternalID:        "CARDEX-" + row.PubULID,
				Make:              row.Make,
				Model:             row.Model,
				Price:             row.PriceEUR,
				FirstRegistration: row.RegDate,
				Mileage:           row.MileageKM,
				FuelType:          row.FuelType,
				Gearbox:           row.Transmission,
				PowerKW:           row.PowerKW,
				Description:       row.Description,
				VIN:               row.VIN,
			})
		}
		xmlBytes, err := xml.MarshalIndent(feed, "", "  ")
		if err != nil {
			slog.Error("publishing.export: mobile.de marshal", "error", err)
			writeError(w, http.StatusInternalServerError, "marshal_error", "failed to generate XML")
			return
		}
		w.Header().Set("Content-Type", "application/xml; charset=UTF-8")
		w.Header().Set("Content-Disposition", `attachment; filename="mobile_de_export.xml"`)
		w.Write([]byte(xml.Header))
		w.Write(xmlBytes)
	}
}

// ── Helpers ────────────────────────────────────────────────────────────────────

func normalizeAS24Fuel(fuel string) string {
	m := map[string]string{
		"gasoline": "B", "petrol": "B", "gasolina": "B", "benzin": "B",
		"diesel": "D", "gasoil": "D",
		"electric": "E", "eléctrico": "E", "elektrisch": "E",
		"hybrid": "H", "híbrido": "H",
		"plug-in hybrid": "P", "phev": "P",
		"lpg": "L", "cng": "C", "hydrogen": "X",
	}
	if v, ok := m[strings.ToLower(fuel)]; ok {
		return v
	}
	return "B" // default: petrol
}

func normalizeAS24Transmission(tr string) string {
	switch strings.ToLower(tr) {
	case "automatic", "automático", "automatik", "dct", "cvt":
		return "A"
	default:
		return "M" // manual
	}
}

func formatToPlatform(format string) string {
	m := map[string]string{
		"wallapop":    "WALLAPOP",
		"coches_net":  "COCHES_NET",
		"mobile_de":   "MOBILE_DE",
		"milanuncios": "MILANUNCIOS",
	}
	if v, ok := m[format]; ok {
		return v
	}
	return strings.ToUpper(format)
}
