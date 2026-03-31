package handlers

import (
	"net/http"
	"strconv"
	"strings"

	meilisearch "github.com/meilisearch/meilisearch-go"
	"github.com/redis/go-redis/v9"
)

// MarketplaceSearch handles GET /api/v1/marketplace/search
// Delegates to MeiliSearch for <50ms full-text + faceted search.
//
// Query params:
//   q          — free text (make, model, description)
//   make       — filter by make (comma-separated)
//   model      — filter by model (comma-separated)
//   year_min   — minimum registration year
//   year_max   — maximum registration year
//   price_min  — minimum price EUR
//   price_max  — maximum price EUR
//   mileage_max — maximum mileage km
//   fuel       — fuel type (PETROL,DIESEL,ELECTRIC,...)
//   tx         — transmission (MANUAL,AUTOMATIC,...)
//   country    — source country (DE,ES,FR,NL,BE,CH)
//   h3_res4    — H3 hex ID for geographic filter
//   sort       — price_eur:asc | price_eur:desc | mileage_km:asc | year:desc
//   page       — page number (1-based)
//   per_page   — results per page (default 24, max 100)
func (d *Deps) MarketplaceSearch(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	query := q.Get("q")
	page := parseInt(q.Get("page"), 1)
	perPage := parseInt(q.Get("per_page"), 24)
	if perPage > 100 {
		perPage = 100
	}

	// Build filter string
	var filters []string
	if v := q.Get("make"); v != "" {
		makes := strings.Split(v, ",")
		var makeFilters []string
		for _, m := range makes {
			makeFilters = append(makeFilters, `make = "`+strings.TrimSpace(m)+`"`)
		}
		filters = append(filters, "("+strings.Join(makeFilters, " OR ")+")")
	}
	if v := q.Get("model"); v != "" {
		models := strings.Split(v, ",")
		var mf []string
		for _, m := range models {
			mf = append(mf, `model = "`+strings.TrimSpace(m)+`"`)
		}
		filters = append(filters, "("+strings.Join(mf, " OR ")+")")
	}
	if v := q.Get("year_min"); v != "" {
		filters = append(filters, "year >= "+v)
	}
	if v := q.Get("year_max"); v != "" {
		filters = append(filters, "year <= "+v)
	}
	if v := q.Get("price_min"); v != "" {
		filters = append(filters, "price_eur >= "+v)
	}
	if v := q.Get("price_max"); v != "" {
		filters = append(filters, "price_eur <= "+v)
	}
	if v := q.Get("mileage_max"); v != "" {
		filters = append(filters, "mileage_km <= "+v)
	}
	if v := q.Get("fuel"); v != "" {
		fuels := strings.Split(v, ",")
		var ff []string
		for _, f := range fuels {
			ff = append(ff, `fuel_type = "`+strings.TrimSpace(f)+`"`)
		}
		filters = append(filters, "("+strings.Join(ff, " OR ")+")")
	}
	if v := q.Get("tx"); v != "" {
		filters = append(filters, `transmission = "`+v+`"`)
	}
	if v := q.Get("country"); v != "" {
		countries := strings.Split(v, ",")
		var cf []string
		for _, c := range countries {
			cf = append(cf, `source_country = "`+strings.TrimSpace(c)+`"`)
		}
		filters = append(filters, "("+strings.Join(cf, " OR ")+")")
	}
	if v := q.Get("h3_res4"); v != "" {
		filters = append(filters, `h3_res4 = "`+v+`"`)
	}
	// Only active listings
	filters = append(filters, `listing_status = "ACTIVE"`)

	filterStr := strings.Join(filters, " AND ")

	// Sort
	var sort []string
	if sv := q.Get("sort"); sv != "" {
		// e.g. "price_eur:asc"
		sort = []string{sv}
	}

	// Facets for the sidebar
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
		"hits":            resp.Hits,
		"total_hits":      resp.TotalHits,
		"page":            resp.Page,
		"total_pages":     resp.TotalPages,
		"facet_distribution": resp.FacetDistribution,
		"processing_time_ms": resp.ProcessingTimeMs,
	})
}

// ListingDetail handles GET /api/v1/marketplace/listing/{ulid}
// Returns full listing data from PostgreSQL (richer than MeiliSearch index).
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
	// TODO: decode body, insert into price_alerts table
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
}

// ListPriceAlerts handles GET /api/v1/marketplace/alerts (authenticated)
func (d *Deps) ListPriceAlerts(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]string{"status": "coming_soon"})
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
