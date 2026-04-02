package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/cardex/api/internal/middleware"
	"github.com/oklog/ulid/v2"
)

// notificationRow is the wire format for a single notification.
type notificationRow struct {
	NotificationULID string          `json:"notification_ulid"`
	Type             string          `json:"type"`
	Title            string          `json:"title"`
	Body             string          `json:"body"`
	ActionURL        *string         `json:"action_url,omitempty"`
	Data             json.RawMessage `json:"data"`
	ReadAt           *string         `json:"read_at,omitempty"`
	CreatedAt        string          `json:"created_at"`
}

// ── NotificationList GET /api/v1/dealer/notifications ─────────────────────────
// Query params: unread_only=true, limit (default 50, max 200), offset
func (d *Deps) NotificationList(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	q := r.URL.Query()
	limit := parseInt(q.Get("limit"), 50)
	if limit > 200 {
		limit = 200
	}
	offset := parseInt(q.Get("offset"), 0)
	unreadOnly := q.Get("unread_only") == "true" || q.Get("unread_only") == "1"

	where := "entity_ulid = $1"
	args := []any{entityULID}
	if unreadOnly {
		where += " AND read_at IS NULL"
	}
	args = append(args, limit, offset)

	rows, err := d.DB.Query(r.Context(),
		`SELECT notification_ulid, type, title, body, action_url, data, read_at::text, created_at::text
		 FROM notifications
		 WHERE `+where+`
		 ORDER BY created_at DESC
		 LIMIT $`+itoa(len(args)-1)+` OFFSET $`+itoa(len(args)),
		args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	var notifs []notificationRow
	for rows.Next() {
		var n notificationRow
		var dataRaw []byte
		if rows.Scan(&n.NotificationULID, &n.Type, &n.Title, &n.Body,
			&n.ActionURL, &dataRaw, &n.ReadAt, &n.CreatedAt) == nil {
			if dataRaw != nil {
				n.Data = json.RawMessage(dataRaw)
			} else {
				n.Data = json.RawMessage(`{}`)
			}
			notifs = append(notifs, n)
		}
	}
	if notifs == nil {
		notifs = []notificationRow{}
	}

	var unreadCount int
	d.DB.QueryRow(r.Context(),
		"SELECT count(*) FROM notifications WHERE entity_ulid=$1 AND read_at IS NULL",
		entityULID).Scan(&unreadCount)

	writeJSON(w, http.StatusOK, map[string]any{
		"notifications": notifs,
		"unread_count":  unreadCount,
		"limit":         limit,
		"offset":        offset,
	})
}

// ── NotificationUnreadCount GET /api/v1/dealer/notifications/unread-count ─────
// Lightweight endpoint polled every 30s by the frontend bell.
func (d *Deps) NotificationUnreadCount(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}

	cacheKey := "notif:unread:" + entityULID
	if cached, err := d.Redis.Get(r.Context(), cacheKey).Result(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"unread_count":` + cached + `}`))
		return
	}

	var count int
	d.DB.QueryRow(r.Context(),
		"SELECT count(*) FROM notifications WHERE entity_ulid=$1 AND read_at IS NULL",
		entityULID).Scan(&count)

	d.Redis.Set(r.Context(), cacheKey, count, 30*time.Second)
	writeJSON(w, http.StatusOK, map[string]int{"unread_count": count})
}

// ── NotificationMarkRead PATCH /api/v1/dealer/notifications/{ulid}/read ───────
func (d *Deps) NotificationMarkRead(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	nULID := r.PathValue("ulid")
	if entityULID == "" || nULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	_, err := d.DB.Exec(r.Context(),
		"UPDATE notifications SET read_at=NOW() WHERE notification_ulid=$1 AND entity_ulid=$2 AND read_at IS NULL",
		nULID, entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	d.Redis.Del(r.Context(), "notif:unread:"+entityULID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "read"})
}

// ── NotificationMarkAllRead POST /api/v1/dealer/notifications/read-all ────────
func (d *Deps) NotificationMarkAllRead(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	if entityULID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing entity context")
		return
	}
	tag, err := d.DB.Exec(r.Context(),
		"UPDATE notifications SET read_at=NOW() WHERE entity_ulid=$1 AND read_at IS NULL",
		entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	d.Redis.Del(r.Context(), "notif:unread:"+entityULID)
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "marked": tag.RowsAffected()})
}

// ── NotificationDelete DELETE /api/v1/dealer/notifications/{ulid} ─────────────
func (d *Deps) NotificationDelete(w http.ResponseWriter, r *http.Request) {
	entityULID := middleware.GetEntityULID(r.Context())
	nULID := r.PathValue("ulid")
	if entityULID == "" || nULID == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "missing params")
		return
	}
	_, err := d.DB.Exec(r.Context(),
		"DELETE FROM notifications WHERE notification_ulid=$1 AND entity_ulid=$2",
		nULID, entityULID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	d.Redis.Del(r.Context(), "notif:unread:"+entityULID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

// ── NotificationPush — internal helper called by other handlers ───────────────
// Inserts a notification and invalidates the unread-count cache.
// Pass data=nil for notifications without extra context.
func (d *Deps) NotificationPush(entityULID, notifType, title, body, actionURL string, data map[string]any) {
	if entityULID == "" || notifType == "" || title == "" {
		return
	}
	dataJSON, _ := json.Marshal(data)
	var actionURLPtr *string
	if actionURL != "" {
		actionURLPtr = &actionURL
	}
	ctx := context.Background()
	id := ulid.Make().String()
	d.DB.Exec(ctx, //nolint
		`INSERT INTO notifications (notification_ulid, entity_ulid, type, title, body, action_url, data)
		 VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		id, entityULID, notifType, title, body, actionURLPtr, dataJSON,
	)
	d.Redis.Del(ctx, "notif:unread:"+entityULID)
}
