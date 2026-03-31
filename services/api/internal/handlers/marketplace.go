package handlers

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"

	meilisearch "github.com/meilisearch/meilisearch-go"
	"github.com/redis/go-redis/v9"
)

// safeFilterValue strips characters that could break MeiliSearch filter syntax.
// MeiliSearch filters use a simple grammar — double quotes wrap string values,
// so we reject any value containing a double-quote or backslash to prevent
// filter injection.
func safeFilterValue(s string) (string, bool) {
	s = strings.TrimSpace(s)
	if s == "" {
		return "", false
	}
	// Reject if it contains filter-special characters
	if strings.ContainsAny(s, `"\\`) {
		return "", false
	}
	// Reject excessively long values (no real make/model/country is >80 chars)
	if len(s) > 80 {
		return "", false
	}
	return s, true
}

// safeNumericFilter validates a numeric filter parameter and returns a filter
// clause like "field >= 1234" or an empty string if invalid.
func safeNumericFilter(field, op, raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	// Accept only digits and an optional single dot (for float prices)
	if ok, _ := regexp.MatchString(`^\d+(\.\d+)?$`, raw); !ok {
		return ""
	}
	return field + " " + op + " " + raw
}

// MarketplaceSearch handles GET /api/v1/marketplace/search
func (d *Deps) MarketplaceSearch(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	query := q.Get("q")
	page := parseInt(q.Get("page"), 1)
	perPage := parseInt(q.Get("per_page"), 24)
	if perPage > 100 {
		perPage = 100
	}

	var filters []string

	// --- String multi-value filters (comma-separated) ---
	if v := q.Get("make"); v != "" {
		var makeFilters []string
		for _, m := range strings.Split(v, ",") {
			if safe, ok := safeFilterValue(m); ok {
				makeFilters = append(makeFilters, `make = "`+safe+`"`)
			}
		}
		if len(makeFilters) > 0 {
			filters = append(filters, "("+strings.Join(makeFilters, " OR ")+")")
		}
	}
	if v := q.Get("model"); v != "" {
		var mf []string
		for _, m := range strings.Split(v, ",") {
			if safe, ok := safeFilterValue(m); ok {
				mf = append(mf, `model = "`+safe+`"`)
			}
		}
		if len(mf) > 0 {
			filters = append(filters, "("+strings.Join(mf, " OR ")+")")
		}
	}
	if v := q.Get("fuel"); v != "" {
		var ff []string
		for _, f := range strings.Split(v, ",") {
			if safe, ok := safeFilterValue(f); ok {
				ff = append(ff, `fuel_type = "`+safe+`"`)
			}
		}
		if len(ff) > 0 {
			filters = append(filters, "("+strings.Join(ff, " OR ")+")")
		}
	}
	if v := q.Get("country"); v != "" {
		var cf []string
		for _, c := range strings.Split(v, ",") {
			if safe, ok := safeFilterValue(c); ok {
				cf = append(cf, `source_country = "`+safe+`"`)
			}
		}
		if len(cf) > 0 {
			filters = append(filters, "("+strings.Join(cf, " OR ")+")")
		}
	}

	// --- Single-value string filters ---
	if v := q.Get("tx"); v != "" {
		if safe, ok := safeFilterValue(v); ok {
			filters = append(filters, `transmission = "`+safe+`"`)
		}
	}
	if v := q.Get("h3_res4"); v != "" {
		if safe, ok := safeFilterValue(v); ok {
			filters = append(filters, `h3_res4 = "`+safe+`"`)
		}
	}

	// --- Numeric range filters (validated — no string injection possible) ---
	if f := safeNumericFilter("year", ">=", q.Get("year_min")); f != "" {
		filters = append(filters, f)
	}
	if f := safeNumericFilter("year", "<=", q.Get("year_max")); f != "" {
		filters = append(filters, f)
	}
	if f := safeNumericFilter("price_eur", ">=", q.Get("price_min")); f != "" {
		filters = append(filters, f)
	}
	if f := safeNumericFilter("price_eur", "<=", q.Get("price_max")); f != "" {
		filters = append(filters, f)
	}
	if f := safeNumericFilter("mileage_km", "<=", q.Get("mileage_max")); f != "" {
		filters = append(filters, f)
	}

	// Always restrict to active listings
	filters = append(filters, `listing_status = "ACTIVE"`)
	filterStr := strings.Join(filters, " AND ")

	// Sort — validate against allowlist
	var sort []string
	allowedSorts := map[string]bool{
		"price_eur:asc": true, "price_eur:desc": true,
		"mileage_km:asc": true, "mileage_km:desc": true,
		"year:asc": true, "year:desc": true,
	}
	if sv := q.Get("sort"); sv != "" && allowedSorts[sv] {
		sort = []string{sv}
	}

	facets := []string{"make", "model", "fuel_type", "transmission", "source_country", "year"}

	resp, err := d.Meili.Search(query, &meilisearch.SearchRequest{
		Filter:               filterStr,
		Sort:                 sort,
		Facets:               facets,
		HitsPerPage:          int64(perPage),
		Page:                 int64(page),
		AttributesToRetrieve: []string{
			"vehicle_ulid", "make", "model", "variant", "year",
			"mileage_km", "price_eur", "fuel_type", "transmission",
			"color", "source_country", "source_url", "thumbnail_url",
			"h3_res4", "listing_status",
		},
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "search_error", err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"hits":               resp.Hits,
		"total_hits":         resp.TotalHits,
		"page":               resp.Page,
		"total_pages":        resp.TotalPages,
		"facet_distribution": resp.FacetDistribution,
		"processing_time_ms": resp.ProcessingTimeMs,
	})
}

// ListingDetail handles GET /api/v1/marketplace/listing/{ulid}
func (d *Deps) ListingDetail(w http.ResponseWriter, r *http.Request) {
	ulid := r.PathValue("ulid")
	if ulid == "" {
		writeError(w, http.StatusBadRequest, "missing_ulid", "vehicle_ulid is required")
		return
	}

	row := d.DB.QueryRow(r.Context(), `
		SELECT
			vehicle_ulid, make, model, variant, year, mileage_km,
			color, fuel_type, transmission, body_type, co2_gkm, power_kw,
			price_raw, currency_raw, gross_physical_cost_eur,
			source_url, source_country, source_platform,
			photo_urls, thumbnail_url,
			listing_status, price_drop_count, last_price_eur,
			seller_type, seller_name,
			city, region, lat, lng, h3_index_res4, h3_index_res7,
			first_seen_at, last_updated_at
		FROM vehicles
		WHERE vehicle_ulid = $1 AND lifecycle_status != 'REJECTED'
	`, ulid)

	var v vehicleRow
	err := row.Scan(
		&v.ULID, &v.Make, &v.Model, &v.Variant, &v.Year, &v.MileageKM,
		&v.Color, &v.FuelType, &v.Transmission, &v.BodyType, &v.CO2GKM, &v.PowerKW,
		&v.PriceRaw, &v.CurrencyRaw, &v.PriceEUR,
		&v.SourceURL, &v.SourceCountry, &v.SourcePlatform,
		&v.PhotoURLs, &v.ThumbnailURL,
		&v.ListingStatus, &v.PriceDropCount, &v.LastPriceEUR,
		&v.SellerType, &v.SellerName,
		&v.City, &v.Region, &v.Lat, &v.Lng, &v.H3Res4, &v.H3Res7,
		&v.FirstSeenAt, &v.LastUpdatedAt,
	)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "listing not found")
		return
	}

	// Track demand signal async (fire-and-forget)
	go func() {
		d.Redis.XAdd(r.Context(), &redis.XAddArgs{
			Stream: "stream:demand_signals",
			Values: map[string]any{
				"make":        v.Make,
				"model":       v.Model,
				"country":     v.SourceCountry,
				"signal_type": "DETAIL_VIEW",
			},
		})
	}()

	writeJSON(w, http.StatusOK, v)
}

// CreatePriceAlert handles POST /api/v1/marketplace/alerts (authenticated)
func (d *Deps) CreatePriceAlert(w http.ResponseWriter, r *http.Request) {
	// JWT sub is stored by Auth middleware as the dealer/user ULID
	userULID := middleware.GetDealerULID(r.Context())
	if userULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "authentication required")
		return
	}

	var body struct {
		Criteria       map[string]any `json:"criteria"`
		TargetPriceEUR *float64       `json:"target_price_eur"`
		Channel        string         `json:"channel"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if len(body.Criteria) == 0 {
		writeError(w, http.StatusBadRequest, "missing_criteria", "criteria is required")
		return
	}
	if body.Channel == "" {
		body.Channel = "EMAIL"
	}
	validChannels := map[string]bool{"EMAIL": true, "PUSH": true, "BOTH": true}
	if !validChannels[body.Channel] {
		writeError(w, http.StatusBadRequest, "invalid_channel", "channel must be EMAIL, PUSH, or BOTH")
		return
	}

	criteriaJSON, err := json.Marshal(body.Criteria)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_criteria", "criteria must be a valid JSON object")
		return
	}

	alertULID := ulid.Make().String()
	_, err = d.DB.Exec(r.Context(), `
		INSERT INTO price_alerts (alert_ulid, user_ulid, criteria, target_price_eur, channel, active)
		VALUES ($1, $2, $3, $4, $5, true)
	`, alertULID, userULID, string(criteriaJSON), body.TargetPriceEUR, body.Channel)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, map[string]string{
		"alert_ulid": alertULID,
		"status":     "created",
	})
}

// ListPriceAlerts handles GET /api/v1/marketplace/alerts (authenticated)
func (d *Deps) ListPriceAlerts(w http.ResponseWriter, r *http.Request) {
	userULID := middleware.GetDealerULID(r.Context())
	if userULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "authentication required")
		return
	}

	rows, err := d.DB.Query(r.Context(), `
		SELECT alert_ulid, criteria, target_price_eur, channel, active, last_fired_at, fire_count, created_at
		FROM price_alerts
		WHERE user_ulid = $1
		ORDER BY created_at DESC
		LIMIT 100
	`, userULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	type alertItem struct {
		ULID           string         `json:"alert_ulid"`
		Criteria       map[string]any `json:"criteria"`
		TargetPrice    *float64       `json:"target_price_eur,omitempty"`
		Channel        string         `json:"channel"`
		Active         bool           `json:"active"`
		LastFiredAt    *string        `json:"last_fired_at,omitempty"`
		FireCount      int            `json:"fire_count"`
		CreatedAt      string         `json:"created_at"`
	}

	var alerts []alertItem
	for rows.Next() {
		var a alertItem
		var criteriaJSON string
		var lastFiredAt *time.Time
		var createdAt time.Time

		if err := rows.Scan(&a.ULID, &criteriaJSON, &a.TargetPrice, &a.Channel, &a.Active, &lastFiredAt, &a.FireCount, &createdAt); err != nil {
			continue
		}
		json.Unmarshal([]byte(criteriaJSON), &a.Criteria)
		a.CreatedAt = createdAt.Format(time.RFC3339)
		if lastFiredAt != nil {
			s := lastFiredAt.Format(time.RFC3339)
			a.LastFiredAt = &s
		}
		alerts = append(alerts, a)
	}
	if alerts == nil {
		alerts = []alertItem{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"alerts": alerts})
}

// DeletePriceAlert handles DELETE /api/v1/marketplace/alerts/{id}
func (d *Deps) DeletePriceAlert(w http.ResponseWriter, r *http.Request) {
	alertULID := r.PathValue("id")
	userULID := middleware.GetDealerULID(r.Context())
	if userULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "authentication required")
		return
	}

	tag, err := d.DB.Exec(r.Context(),
		"UPDATE price_alerts SET active = false WHERE alert_ulid = $1 AND user_ulid = $2",
		alertULID, userULID,
	)
	if err != nil || tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "not_found", "alert not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deactivated"})
}

// vehicleRow is a scan target for the listing detail query.
type vehicleRow struct {
	ULID           string   `json:"vehicle_ulid"`
	Make           *string  `json:"make"`
	Model          *string  `json:"model"`
	Variant        *string  `json:"variant,omitempty"`
	Year           *int     `json:"year"`
	MileageKM      *int     `json:"mileage_km"`
	Color          *string  `json:"color,omitempty"`
	FuelType       *string  `json:"fuel_type,omitempty"`
	Transmission   *string  `json:"transmission,omitempty"`
	BodyType       *string  `json:"body_type,omitempty"`
	CO2GKM         *int     `json:"co2_gkm,omitempty"`
	PowerKW        *int     `json:"power_kw,omitempty"`
	PriceRaw       *float64 `json:"price_raw,omitempty"`
	CurrencyRaw    *string  `json:"currency_raw,omitempty"`
	PriceEUR       *float64 `json:"price_eur"`
	SourceURL      *string  `json:"source_url"`
	SourceCountry  *string  `json:"source_country"`
	SourcePlatform *string  `json:"source_platform"`
	PhotoURLs      []string `json:"photo_urls"`
	ThumbnailURL   *string  `json:"thumbnail_url,omitempty"`
	ListingStatus  *string  `json:"listing_status"`
	PriceDropCount *int     `json:"price_drop_count"`
	LastPriceEUR   *float64 `json:"last_price_eur,omitempty"`
	SellerType     *string  `json:"seller_type,omitempty"`
	SellerName     *string  `json:"seller_name,omitempty"`
	City           *string  `json:"city,omitempty"`
	Region         *string  `json:"region,omitempty"`
	Lat            *float64 `json:"lat,omitempty"`
	Lng            *float64 `json:"lng,omitempty"`
	H3Res4         *string  `json:"h3_res4,omitempty"`
	H3Res7         *string  `json:"h3_res7,omitempty"`
	FirstSeenAt    *string  `json:"first_seen_at"`
	LastUpdatedAt  *string  `json:"last_updated_at"`
}

func parseInt(s string, def int) int {
	if s == "" {
		return def
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return v
}
