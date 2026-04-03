package handlers

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// ── Admin Stats ───────────────────────────────────────────────────────────────

type adminStatsResponse struct {
	TotalEntities       int            `json:"total_entities"`
	TotalUsers          int            `json:"total_users"`
	ActiveListings      int64          `json:"active_listings"`
	ScrapeJobsToday     int            `json:"scrape_jobs_today"`
	NotificationsSent24h int           `json:"notifications_sent_24h"`
	EntitiesByTier      map[string]int `json:"entities_by_tier"`
}

// AdminStats handles GET /api/v1/admin/stats
func (d *Deps) AdminStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var (
		mu   sync.Mutex
		wg   sync.WaitGroup
		resp adminStatsResponse
	)
	resp.EntitiesByTier = map[string]int{}

	wg.Add(6)

	// total_entities
	go func() {
		defer wg.Done()
		var count int
		if err := d.DB.QueryRow(ctx, `SELECT COUNT(*) FROM entities WHERE active = true`).Scan(&count); err != nil {
			slog.Warn("admin.stats: total_entities scan", "error", err)
		}
		mu.Lock()
		resp.TotalEntities = count
		mu.Unlock()
	}()

	// total_users
	go func() {
		defer wg.Done()
		var count int
		if err := d.DB.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&count); err != nil {
			slog.Warn("admin.stats: total_users scan", "error", err)
		}
		mu.Lock()
		resp.TotalUsers = count
		mu.Unlock()
	}()

	// active_listings from ClickHouse
	go func() {
		defer wg.Done()
		var count int64
		row := d.CH.QueryRow(ctx, `SELECT count() FROM cardex.vehicle_inventory WHERE lifecycle_status = 'ACTIVE'`)
		if err := row.Scan(&count); err != nil {
			slog.Warn("admin.stats: active_listings scan", "error", err)
		}
		mu.Lock()
		resp.ActiveListings = count
		mu.Unlock()
	}()

	// scrape_jobs_today
	go func() {
		defer wg.Done()
		var count int
		if err := d.DB.QueryRow(ctx, `SELECT COUNT(*) FROM scrape_jobs WHERE created_at >= CURRENT_DATE`).Scan(&count); err != nil {
			slog.Warn("admin.stats: scrape_jobs_today scan", "error", err)
		}
		mu.Lock()
		resp.ScrapeJobsToday = count
		mu.Unlock()
	}()

	// notifications_sent_24h
	go func() {
		defer wg.Done()
		var count int
		if err := d.DB.QueryRow(ctx, `SELECT COUNT(*) FROM notifications WHERE created_at >= NOW() - INTERVAL '24 hours'`).Scan(&count); err != nil {
			slog.Warn("admin.stats: notifications_24h scan", "error", err)
		}
		mu.Lock()
		resp.NotificationsSent24h = count
		mu.Unlock()
	}()

	// entities_by_tier
	go func() {
		defer wg.Done()
		rows, err := d.DB.Query(ctx, `SELECT subscription_tier, COUNT(*) FROM entities GROUP BY subscription_tier`)
		if err != nil {
			slog.Warn("admin.stats: entities_by_tier query", "error", err)
			return
		}
		defer rows.Close()
		tiers := map[string]int{}
		for rows.Next() {
			var tier string
			var count int
			if err := rows.Scan(&tier, &count); err != nil {
				continue
			}
			tiers[tier] = count
		}
		mu.Lock()
		resp.EntitiesByTier = tiers
		mu.Unlock()
	}()

	wg.Wait()
	writeJSON(w, http.StatusOK, resp)
}

// ── Admin Entity List ─────────────────────────────────────────────────────────

type adminEntityRow struct {
	EntityULID        string    `json:"entity_ulid"`
	LegalName         string    `json:"legal_name"`
	CountryCode       string    `json:"country_code"`
	SubscriptionTier  string    `json:"subscription_tier"`
	CreatedAt         time.Time `json:"created_at"`
	UserCount         int       `json:"user_count"`
}

type adminEntityListResponse struct {
	Entities []adminEntityRow `json:"entities"`
	Total    int              `json:"total"`
}

// AdminEntityList handles GET /api/v1/admin/entities
func (d *Deps) AdminEntityList(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	q := r.URL.Query()

	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 50
	}
	offset, _ := strconv.Atoi(q.Get("offset"))
	tier := q.Get("tier")
	search := q.Get("search")

	var whereClauses []string
	var args []any
	argIdx := 1

	if tier != "" {
		whereClauses = append(whereClauses, "e.subscription_tier = $"+strconv.Itoa(argIdx))
		args = append(args, tier)
		argIdx++
	}
	if search != "" {
		whereClauses = append(whereClauses, "(e.legal_name ILIKE $"+strconv.Itoa(argIdx)+" OR e.contact_email ILIKE $"+strconv.Itoa(argIdx)+")")
		args = append(args, "%"+search+"%")
		argIdx++
	}

	whereSQL := ""
	if len(whereClauses) > 0 {
		whereSQL = " WHERE " + joinStrings(whereClauses, " AND ")
	}

	countQuery := `SELECT COUNT(*) FROM entities e` + whereSQL
	var total int
	_ = d.DB.QueryRow(ctx, countQuery, args...).Scan(&total)

	dataArgs := append(args, limit, offset)
	dataQuery := `
SELECT e.entity_ulid, e.legal_name, e.country_code, e.subscription_tier, e.onboarded_at,
       COUNT(u.user_ulid) AS user_count
FROM entities e
LEFT JOIN users u ON u.entity_ulid = e.entity_ulid` + whereSQL + `
GROUP BY e.entity_ulid, e.legal_name, e.country_code, e.subscription_tier, e.onboarded_at
ORDER BY e.onboarded_at DESC
LIMIT $` + strconv.Itoa(argIdx) + ` OFFSET $` + strconv.Itoa(argIdx+1)

	rows, err := d.DB.Query(ctx, dataQuery, dataArgs...)
	if err != nil {
		slog.Error("admin.entity-list: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	var entities []adminEntityRow
	for rows.Next() {
		var row adminEntityRow
		if err := rows.Scan(&row.EntityULID, &row.LegalName, &row.CountryCode,
			&row.SubscriptionTier, &row.CreatedAt, &row.UserCount); err != nil {
			slog.Warn("admin.entity-list: row scan", "error", err)
			continue
		}
		entities = append(entities, row)
	}
	if entities == nil {
		entities = []adminEntityRow{}
	}
	writeJSON(w, http.StatusOK, adminEntityListResponse{Entities: entities, Total: total})
}

// ── Admin Entity Update ───────────────────────────────────────────────────────

type adminEntityUpdateRequest struct {
	SubscriptionTier *string `json:"subscription_tier"`
	Active           *bool   `json:"active"`
}

// AdminEntityUpdate handles PATCH /api/v1/admin/entities/{ulid}
func (d *Deps) AdminEntityUpdate(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	entityULID := r.PathValue("ulid")
	if entityULID == "" {
		writeError(w, http.StatusBadRequest, "missing_ulid", "entity ulid required")
		return
	}

	var req adminEntityUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", "invalid JSON body")
		return
	}

	var setClauses []string
	var args []any
	argIdx := 1

	if req.SubscriptionTier != nil {
		setClauses = append(setClauses, "subscription_tier = $"+strconv.Itoa(argIdx))
		args = append(args, *req.SubscriptionTier)
		argIdx++
	}
	if req.Active != nil {
		setClauses = append(setClauses, "active = $"+strconv.Itoa(argIdx))
		args = append(args, *req.Active)
		argIdx++
	}

	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "no_fields", "no fields to update")
		return
	}

	setClauses = append(setClauses, "updated_at = NOW()")
	args = append(args, entityULID)

	query := "UPDATE entities SET " + joinStrings(setClauses, ", ") + " WHERE entity_ulid = $" + strconv.Itoa(argIdx)
	_, err := d.DB.Exec(ctx, query, args...)
	if err != nil {
		slog.Error("admin.entity-update: exec", "error", err)
		writeError(w, http.StatusInternalServerError, "db_error", "failed to update entity")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// ── Admin User List ───────────────────────────────────────────────────────────

type adminUserRow struct {
	UserULID      string    `json:"user_ulid"`
	Email         string    `json:"email"`
	FullName      string    `json:"full_name"`
	EntityULID    string    `json:"entity_ulid"`
	IsDealer      bool      `json:"is_dealer"`
	EmailVerified bool      `json:"email_verified"`
	CreatedAt     time.Time `json:"created_at"`
}

type adminUserListResponse struct {
	Users []adminUserRow `json:"users"`
	Total int            `json:"total"`
}

// AdminUserList handles GET /api/v1/admin/users
func (d *Deps) AdminUserList(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	q := r.URL.Query()

	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 50
	}
	offset, _ := strconv.Atoi(q.Get("offset"))
	entityFilter := q.Get("entity_ulid")
	search := q.Get("search")

	var whereClauses []string
	var args []any
	argIdx := 1

	if entityFilter != "" {
		whereClauses = append(whereClauses, "entity_ulid = $"+strconv.Itoa(argIdx))
		args = append(args, entityFilter)
		argIdx++
	}
	if search != "" {
		whereClauses = append(whereClauses, "(email ILIKE $"+strconv.Itoa(argIdx)+" OR full_name ILIKE $"+strconv.Itoa(argIdx)+")")
		args = append(args, "%"+search+"%")
		argIdx++
	}

	whereSQL := ""
	if len(whereClauses) > 0 {
		whereSQL = " WHERE " + joinStrings(whereClauses, " AND ")
	}

	var total int
	_ = d.DB.QueryRow(ctx, `SELECT COUNT(*) FROM users`+whereSQL, args...).Scan(&total)

	dataArgs := append(args, limit, offset)
	dataQuery := `
SELECT user_ulid, email, COALESCE(full_name,''), COALESCE(entity_ulid,''),
       COALESCE(is_dealer, false), (email_verified_at IS NOT NULL), created_at
FROM users` + whereSQL + `
ORDER BY created_at DESC
LIMIT $` + strconv.Itoa(argIdx) + ` OFFSET $` + strconv.Itoa(argIdx+1)

	rows, err := d.DB.Query(ctx, dataQuery, dataArgs...)
	if err != nil {
		slog.Error("admin.user-list: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	var users []adminUserRow
	for rows.Next() {
		var row adminUserRow
		if err := rows.Scan(&row.UserULID, &row.Email, &row.FullName, &row.EntityULID,
			&row.IsDealer, &row.EmailVerified, &row.CreatedAt); err != nil {
			slog.Warn("admin.user-list: row scan", "error", err)
			continue
		}
		users = append(users, row)
	}
	if users == nil {
		users = []adminUserRow{}
	}
	writeJSON(w, http.StatusOK, adminUserListResponse{Users: users, Total: total})
}

// ── Admin Scraper Status ──────────────────────────────────────────────────────

type scraperRow struct {
	Platform       string     `json:"platform"`
	Status         string     `json:"status"`
	RecordsFetched int        `json:"records_fetched"`
	StartedAt      *time.Time `json:"started_at"`
	CompletedAt    *time.Time `json:"completed_at"`
	LagMinutes     *int       `json:"lag_minutes"`
}

// AdminScraperStatus handles GET /api/v1/admin/scrapers
func (d *Deps) AdminScraperStatus(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	query := `
SELECT DISTINCT ON (platform)
    platform,
    COALESCE(status,'UNKNOWN'),
    COALESCE(records_fetched,0),
    started_at,
    completed_at
FROM scrape_jobs
ORDER BY platform, started_at DESC`

	rows, err := d.DB.Query(ctx, query)
	if err != nil {
		slog.Error("admin.scrapers: query", "error", err)
		writeError(w, http.StatusServiceUnavailable, "db_unavailable", "database temporarily unavailable")
		return
	}
	defer rows.Close()

	now := time.Now()
	var scrapers []scraperRow
	for rows.Next() {
		var row scraperRow
		if err := rows.Scan(&row.Platform, &row.Status, &row.RecordsFetched,
			&row.StartedAt, &row.CompletedAt); err != nil {
			slog.Warn("admin.scrapers: row scan", "error", err)
			continue
		}
		if row.CompletedAt != nil {
			lag := int(now.Sub(*row.CompletedAt).Minutes())
			row.LagMinutes = &lag
		}
		scrapers = append(scrapers, row)
	}
	if scrapers == nil {
		scrapers = []scraperRow{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"scrapers": scrapers})
}

// ── helpers ───────────────────────────────────────────────────────────────────

func joinStrings(parts []string, sep string) string {
	if len(parts) == 0 {
		return ""
	}
	result := parts[0]
	for _, p := range parts[1:] {
		result += sep + p
	}
	return result
}
