package kanban_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"log/slog"

	"cardex.eu/workspace/internal/kanban"
)

// ── Helpers ───────────────────────────────────────────────────────────────────

func openDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func newStore(t *testing.T) *kanban.Store {
	t.Helper()
	s, err := kanban.NewStore(openDB(t))
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	return s
}

func discardLog() *slog.Logger {
	return slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
}

const tenant = "t1"

func ctx() context.Context { return context.Background() }

// Seed a column+card so we have something to move/patch.
func seedColumn(t *testing.T, s *kanban.Store, name, stateKey string, pos int) kanban.Column {
	t.Helper()
	col, err := s.CreateColumn(ctx(), tenant, name, "#AABBCC", 0, pos)
	if err != nil {
		t.Fatalf("CreateColumn %q: %v", name, err)
	}
	// inject state_key directly — CreateColumn doesn't expose it; use the DB.
	// For tests without state_key we're fine; those with state_key use InitTenant.
	_ = stateKey
	return col
}

// ── Schema ────────────────────────────────────────────────────────────────────

func TestEnsureSchema_Idempotent(t *testing.T) {
	db := openDB(t)
	if err := kanban.EnsureSchema(db); err != nil {
		t.Fatalf("first call: %v", err)
	}
	if err := kanban.EnsureSchema(db); err != nil {
		t.Fatalf("second call (idempotent): %v", err)
	}
}

// ── Default columns ───────────────────────────────────────────────────────────

func TestDefaultColumns_Count(t *testing.T) {
	cols := kanban.DefaultColumns(tenant)
	if len(cols) != 11 {
		t.Errorf("want 11 default columns, got %d", len(cols))
	}
}

func TestDefaultColumns_UniquePositions(t *testing.T) {
	cols := kanban.DefaultColumns(tenant)
	seen := map[int]bool{}
	for _, c := range cols {
		if seen[c.Position] {
			t.Errorf("duplicate position %d", c.Position)
		}
		seen[c.Position] = true
	}
}

func TestDefaultColumns_AllDefault(t *testing.T) {
	for _, c := range kanban.DefaultColumns(tenant) {
		if !c.IsDefault {
			t.Errorf("column %q should be is_default=true", c.Name)
		}
	}
}

// ── Column CRUD ───────────────────────────────────────────────────────────────

func TestInitTenant_CreatesColumns(t *testing.T) {
	s := newStore(t)
	if err := s.InitTenant(ctx(), tenant); err != nil {
		t.Fatalf("InitTenant: %v", err)
	}
	cols, err := s.ListColumns(ctx(), tenant)
	if err != nil {
		t.Fatalf("ListColumns: %v", err)
	}
	if len(cols) != 11 {
		t.Errorf("want 11 columns after init, got %d", len(cols))
	}
}

func TestInitTenant_Idempotent(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	s.InitTenant(ctx(), tenant) // second call must not duplicate
	cols, _ := s.ListColumns(ctx(), tenant)
	if len(cols) != 11 {
		t.Errorf("want 11 columns (idempotent), got %d", len(cols))
	}
}

func TestCreateColumn_Success(t *testing.T) {
	s := newStore(t)
	col, err := s.CreateColumn(ctx(), tenant, "Custom Stage", "#FF0000", 5, 99)
	if err != nil {
		t.Fatalf("CreateColumn: %v", err)
	}
	if col.Name != "Custom Stage" {
		t.Errorf("want name='Custom Stage', got %q", col.Name)
	}
	if col.Color != "#FF0000" {
		t.Errorf("want color=#FF0000, got %q", col.Color)
	}
}

func TestCreateColumn_EmptyNameError(t *testing.T) {
	s := newStore(t)
	_, err := s.CreateColumn(ctx(), tenant, "", "#AAAAAA", 0, 1)
	if err == nil {
		t.Error("want error for empty name, got nil")
	}
}

func TestCreateColumn_InvalidColorDefaulted(t *testing.T) {
	s := newStore(t)
	col, err := s.CreateColumn(ctx(), tenant, "Stage", "bad-color", 0, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if col.Color != "#6B7280" {
		t.Errorf("want default color, got %q", col.Color)
	}
}

func TestPatchColumn_Name(t *testing.T) {
	s := newStore(t)
	col := seedColumn(t, s, "Old Name", "", 1)
	newName := "New Name"
	updated, err := s.PatchColumn(ctx(), tenant, col.ID, kanban.ColumnPatch{Name: &newName})
	if err != nil {
		t.Fatalf("PatchColumn: %v", err)
	}
	if updated.Name != "New Name" {
		t.Errorf("want 'New Name', got %q", updated.Name)
	}
}

func TestPatchColumn_WIPLimit(t *testing.T) {
	s := newStore(t)
	col := seedColumn(t, s, "Stage", "", 1)
	limit := 10
	updated, _ := s.PatchColumn(ctx(), tenant, col.ID, kanban.ColumnPatch{VehicleLimit: &limit})
	if updated.VehicleLimit != 10 {
		t.Errorf("want vehicle_limit=10, got %d", updated.VehicleLimit)
	}
}

func TestPatchColumn_NotFound(t *testing.T) {
	s := newStore(t)
	name := "x"
	_, err := s.PatchColumn(ctx(), tenant, "nonexistent", kanban.ColumnPatch{Name: &name})
	if err == nil {
		t.Error("want error for non-existent column")
	}
}

// ── Kanban cards ──────────────────────────────────────────────────────────────

func TestEnsureCard_CreatesCard(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	cols, _ := s.ListColumns(ctx(), tenant)
	col := cols[0]
	if err := s.EnsureCard(ctx(), tenant, "veh-001", col.ID, 0); err != nil {
		t.Fatalf("EnsureCard: %v", err)
	}
	updated, _ := s.ListColumns(ctx(), tenant)
	found := false
	for _, c := range updated[0].Cards {
		if c.VehicleID == "veh-001" {
			found = true
		}
	}
	if !found {
		t.Error("card not found in column after EnsureCard")
	}
}

func TestEnsureCard_Idempotent(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	cols, _ := s.ListColumns(ctx(), tenant)
	colID := cols[0].ID
	s.EnsureCard(ctx(), tenant, "veh-002", colID, 0)
	s.EnsureCard(ctx(), tenant, "veh-002", colID, 1) // upsert
	updated, _ := s.ListColumns(ctx(), tenant)
	count := 0
	for _, c := range updated[0].Cards {
		if c.VehicleID == "veh-002" {
			count++
		}
	}
	if count != 1 {
		t.Errorf("want 1 card (idempotent), got %d", count)
	}
}

func TestMoveCard_ValidTransition(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	cols, _ := s.ListColumns(ctx(), tenant)
	// Find "listed" (index 4) and "inquiry" (index 5) columns.
	var listedCol, inquiryCol kanban.Column
	for _, c := range cols {
		switch c.Name {
		case "Listed":
			listedCol = c
		case "Inquiry":
			inquiryCol = c
		}
	}
	s.EnsureCard(ctx(), tenant, "veh-t1", listedCol.ID, 0)
	card, err := s.MoveCard(ctx(), tenant, "veh-t1", kanban.MoveRequest{
		TargetColumnID: inquiryCol.ID,
		Position:       0,
	})
	if err != nil {
		t.Fatalf("MoveCard listed→inquiry: %v", err)
	}
	if card.ColumnID != inquiryCol.ID {
		t.Errorf("want card in inquiry column, got %q", card.ColumnID)
	}
}

func TestMoveCard_InvalidTransition(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	cols, _ := s.ListColumns(ctx(), tenant)
	var sourcingCol, soldCol kanban.Column
	for _, c := range cols {
		switch c.Name {
		case "Sourcing":
			sourcingCol = c
		case "Sold":
			soldCol = c
		}
	}
	s.EnsureCard(ctx(), tenant, "veh-inv", sourcingCol.ID, 0)
	_, err := s.MoveCard(ctx(), tenant, "veh-inv", kanban.MoveRequest{
		TargetColumnID: soldCol.ID,
		Position:       0,
	})
	if err == nil {
		t.Error("want error for invalid state transition sourcing→sold")
	}
}

func TestMoveCard_WIPLimitEnforced(t *testing.T) {
	s := newStore(t)
	limit := 1
	col, _ := s.CreateColumn(ctx(), tenant, "Limited", "#AAAAAA", limit, 1)
	col2, _ := s.CreateColumn(ctx(), tenant, "Source", "#BBBBBB", 0, 2)
	s.EnsureCard(ctx(), tenant, "veh-a", col.ID, 0) // fill the column
	s.EnsureCard(ctx(), tenant, "veh-b", col2.ID, 0)
	_, err := s.MoveCard(ctx(), tenant, "veh-b", kanban.MoveRequest{
		TargetColumnID: col.ID,
		Position:       1,
	})
	if err == nil {
		t.Error("want WIP limit error, got nil")
	}
	if !strings.Contains(err.Error(), "WIP limit") {
		t.Errorf("want WIP limit message, got: %v", err)
	}
}

func TestMoveCard_CardNotFound(t *testing.T) {
	s := newStore(t)
	s.InitTenant(ctx(), tenant)
	cols, _ := s.ListColumns(ctx(), tenant)
	_, err := s.MoveCard(ctx(), tenant, "ghost-veh", kanban.MoveRequest{
		TargetColumnID: cols[1].ID,
	})
	if err == nil {
		t.Error("want error for non-existent card")
	}
}

func TestPatchCard_Priority(t *testing.T) {
	s := newStore(t)
	col, _ := s.CreateColumn(ctx(), tenant, "Stage", "#AAAAAA", 0, 1)
	s.EnsureCard(ctx(), tenant, "veh-p", col.ID, 0)
	pri := "urgent"
	card, err := s.PatchCard(ctx(), tenant, "veh-p", kanban.CardPatch{Priority: &pri})
	if err != nil {
		t.Fatalf("PatchCard: %v", err)
	}
	if card.Priority != "urgent" {
		t.Errorf("want priority=urgent, got %s", card.Priority)
	}
}

func TestPatchCard_InvalidPriority(t *testing.T) {
	s := newStore(t)
	col, _ := s.CreateColumn(ctx(), tenant, "Stage", "#AAAAAA", 0, 1)
	s.EnsureCard(ctx(), tenant, "veh-px", col.ID, 0)
	bad := "extreme"
	_, err := s.PatchCard(ctx(), tenant, "veh-px", kanban.CardPatch{Priority: &bad})
	if err == nil {
		t.Error("want error for invalid priority")
	}
}

func TestPatchCard_Labels(t *testing.T) {
	s := newStore(t)
	col, _ := s.CreateColumn(ctx(), tenant, "Stage", "#AAAAAA", 0, 1)
	s.EnsureCard(ctx(), tenant, "veh-l", col.ID, 0)
	card, err := s.PatchCard(ctx(), tenant, "veh-l", kanban.CardPatch{Labels: []string{"ev", "priority"}})
	if err != nil {
		t.Fatalf("PatchCard labels: %v", err)
	}
	if len(card.Labels) != 2 || card.Labels[0] != "ev" {
		t.Errorf("unexpected labels: %v", card.Labels)
	}
}

// ── State machine ─────────────────────────────────────────────────────────────

func TestValidateTransition_AllowedPairs(t *testing.T) {
	pairs := [][2]string{
		{"sourcing", "acquired"},
		{"acquired", "reconditioning"},
		{"listed", "inquiry"},
		{"inquiry", "negotiation"},
		{"negotiation", "reserved"},
		{"reserved", "sold"},
		{"sold", "in_transit"},
		{"in_transit", "delivered"},
	}
	for _, p := range pairs {
		if err := kanban.ValidateTransition(p[0], p[1]); err != nil {
			t.Errorf("want %s→%s to be allowed, got error: %v", p[0], p[1], err)
		}
	}
}

func TestValidateTransition_ForbiddenPairs(t *testing.T) {
	pairs := [][2]string{
		{"sourcing", "sold"},
		{"delivered", "sourcing"},
		{"in_transit", "listed"},
		{"sold", "listed"},
	}
	for _, p := range pairs {
		if err := kanban.ValidateTransition(p[0], p[1]); err == nil {
			t.Errorf("want %s→%s to be forbidden, got nil", p[0], p[1])
		}
	}
}

func TestValidateTransition_UnknownState(t *testing.T) {
	err := kanban.ValidateTransition("ghost", "listed")
	if err == nil {
		t.Error("want error for unknown state")
	}
}

// ── Calendar events ───────────────────────────────────────────────────────────

func futureRFC3339(days int) string {
	return time.Now().UTC().Add(time.Duration(days) * 24 * time.Hour).Format(time.RFC3339)
}

func TestCreateEvent_Success(t *testing.T) {
	s := newStore(t)
	e := kanban.Event{
		TenantID:  tenant,
		Title:     "Client Meeting",
		EventType: "client_meeting",
		StartAt:   futureRFC3339(1),
		EndAt:     futureRFC3339(1),
	}
	created, err := s.CreateEvent(ctx(), e)
	if err != nil {
		t.Fatalf("CreateEvent: %v", err)
	}
	if created.ID == "" {
		t.Error("want non-empty event ID")
	}
	if created.Status != "scheduled" {
		t.Errorf("want status=scheduled, got %q", created.Status)
	}
}

func TestCreateEvent_MissingTitle(t *testing.T) {
	s := newStore(t)
	_, err := s.CreateEvent(ctx(), kanban.Event{
		TenantID: tenant,
		StartAt:  futureRFC3339(1),
		EndAt:    futureRFC3339(1),
	})
	if err == nil {
		t.Error("want error for missing title")
	}
}

func TestCreateEvent_MissingTimestamps(t *testing.T) {
	s := newStore(t)
	_, err := s.CreateEvent(ctx(), kanban.Event{
		TenantID:  tenant,
		Title:     "X",
		EventType: "other",
	})
	if err == nil {
		t.Error("want error for missing start_at/end_at")
	}
}

func TestCreateEvent_UnknownTypeDefaultsToOther(t *testing.T) {
	s := newStore(t)
	e, err := s.CreateEvent(ctx(), kanban.Event{
		TenantID:  tenant,
		Title:     "Mystery",
		EventType: "mystery_type",
		StartAt:   futureRFC3339(1),
		EndAt:     futureRFC3339(1),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if e.EventType != "other" {
		t.Errorf("want event_type=other for unknown type, got %q", e.EventType)
	}
}

func TestListEvents_RangeFilter(t *testing.T) {
	s := newStore(t)
	// Create events on day 2 and day 10.
	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "E1", EventType: "other",
		StartAt: futureRFC3339(2), EndAt: futureRFC3339(2)})
	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "E2", EventType: "other",
		StartAt: futureRFC3339(10), EndAt: futureRFC3339(10)})

	// Only query day 1–5.
	events, err := s.ListEvents(ctx(), tenant, futureRFC3339(0), futureRFC3339(5))
	if err != nil {
		t.Fatalf("ListEvents: %v", err)
	}
	if len(events) != 1 || events[0].Title != "E1" {
		t.Errorf("want 1 event in range, got %d: %v", len(events), events)
	}
}

func TestListEvents_ExcludesCancelled(t *testing.T) {
	s := newStore(t)
	e, _ := s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Cancel me",
		EventType: "other", StartAt: futureRFC3339(1), EndAt: futureRFC3339(1)})
	s.CancelEvent(ctx(), tenant, e.ID)

	events, _ := s.ListEvents(ctx(), tenant, "", "")
	for _, ev := range events {
		if ev.ID == e.ID {
			t.Error("cancelled event should not appear in list")
		}
	}
}

func TestPatchEvent_TitleAndStatus(t *testing.T) {
	s := newStore(t)
	e, _ := s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Old",
		EventType: "other", StartAt: futureRFC3339(1), EndAt: futureRFC3339(1)})
	newTitle := "Updated"
	newStatus := "completed"
	updated, err := s.PatchEvent(ctx(), tenant, e.ID, kanban.EventPatch{Title: &newTitle, Status: &newStatus})
	if err != nil {
		t.Fatalf("PatchEvent: %v", err)
	}
	if updated.Title != "Updated" {
		t.Errorf("want title=Updated, got %q", updated.Title)
	}
	if updated.Status != "completed" {
		t.Errorf("want status=completed, got %q", updated.Status)
	}
}

func TestPatchEvent_NotFound(t *testing.T) {
	s := newStore(t)
	title := "x"
	_, err := s.PatchEvent(ctx(), tenant, "ghost-event", kanban.EventPatch{Title: &title})
	if err == nil {
		t.Error("want error for non-existent event")
	}
}

func TestCancelEvent_SetsStatus(t *testing.T) {
	s := newStore(t)
	e, _ := s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "To cancel",
		EventType: "other", StartAt: futureRFC3339(1), EndAt: futureRFC3339(1)})
	if err := s.CancelEvent(ctx(), tenant, e.ID); err != nil {
		t.Fatalf("CancelEvent: %v", err)
	}
}

func TestCancelEvent_NotFound(t *testing.T) {
	s := newStore(t)
	if err := s.CancelEvent(ctx(), tenant, "ghost"); err == nil {
		t.Error("want error for non-existent event")
	}
}

// ── Auto-generated events ─────────────────────────────────────────────────────

func TestAutoEvent_InTransit(t *testing.T) {
	s := newStore(t)
	if err := s.OnVehicleStateChange(ctx(), tenant, "veh-transit", "in_transit"); err != nil {
		t.Fatalf("OnVehicleStateChange in_transit: %v", err)
	}
	events, _ := s.ListEvents(ctx(), tenant, "", "")
	found := false
	for _, e := range events {
		if e.EventType == "transport_delivery" && e.AutoGenerated {
			found = true
		}
	}
	if !found {
		t.Error("want auto-generated transport_delivery event")
	}
}

func TestAutoEvent_Reserved(t *testing.T) {
	s := newStore(t)
	if err := s.OnVehicleStateChange(ctx(), tenant, "veh-res", "reserved"); err != nil {
		t.Fatalf("OnVehicleStateChange reserved: %v", err)
	}
	events, _ := s.ListEvents(ctx(), tenant, "", "")
	found := false
	for _, e := range events {
		if e.EventType == "registration" && e.AutoGenerated {
			found = true
		}
	}
	if !found {
		t.Error("want auto-generated registration event")
	}
}

func TestAutoEvent_NoTriggerForOtherStates(t *testing.T) {
	s := newStore(t)
	if err := s.OnVehicleStateChange(ctx(), tenant, "veh-x", "listed"); err != nil {
		t.Fatalf("OnVehicleStateChange: %v", err)
	}
	events, _ := s.ListEvents(ctx(), tenant, "", "")
	if len(events) != 0 {
		t.Errorf("want no auto-events for 'listed' state, got %d", len(events))
	}
}

func TestUpcomingEvents_DefaultDays(t *testing.T) {
	s := newStore(t)
	// Event in 3 days (should appear) and 10 days (outside 7-day window).
	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Soon",
		EventType: "other", StartAt: futureRFC3339(3), EndAt: futureRFC3339(3)})
	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Far",
		EventType: "other", StartAt: futureRFC3339(10), EndAt: futureRFC3339(10)})

	events, err := s.UpcomingEvents(ctx(), tenant, 7)
	if err != nil {
		t.Fatalf("UpcomingEvents: %v", err)
	}
	if len(events) != 1 || events[0].Title != "Soon" {
		t.Errorf("want 1 upcoming event (Soon), got %d: %v", len(events), events)
	}
}

// ── HTTP handler tests ────────────────────────────────────────────────────────

func newTestServer(t *testing.T) (*kanban.Server, *kanban.Store) {
	t.Helper()
	s := newStore(t)
	srv := kanban.NewServer(s, discardLog())
	return srv, s
}

func TestHTTP_GetColumns(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/kanban/columns", nil)
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	var cols []kanban.Column
	if err := json.NewDecoder(w.Body).Decode(&cols); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(cols) != 11 {
		t.Errorf("want 11 default columns, got %d", len(cols))
	}
}

func TestHTTP_CreateColumn(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	body := `{"name":"Auction","color":"#FF6600","vehicle_limit":5,"position":99}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/kanban/columns", strings.NewReader(body))
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("want 201, got %d: %s", w.Code, w.Body.String())
	}
}

func TestHTTP_MissingTenantID(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/kanban/columns", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400 for missing tenant, got %d", w.Code)
	}
}

func TestHTTP_CreateEvent(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	body := `{"title":"Inspection","event_type":"inspection","start_at":"` +
		futureRFC3339(2) + `","end_at":"` + futureRFC3339(2) + `"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/calendar/events", strings.NewReader(body))
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("want 201, got %d: %s", w.Code, w.Body.String())
	}
	var e kanban.Event
	json.NewDecoder(w.Body).Decode(&e)
	if e.ID == "" {
		t.Error("response should include event ID")
	}
}

func TestHTTP_GetEvents(t *testing.T) {
	srv, s := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Meet",
		EventType: "client_meeting", StartAt: futureRFC3339(1), EndAt: futureRFC3339(1)})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/calendar/events", nil)
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", w.Code)
	}
	var events []kanban.Event
	json.NewDecoder(w.Body).Decode(&events)
	if len(events) != 1 {
		t.Errorf("want 1 event, got %d", len(events))
	}
}

func TestHTTP_DeleteEvent(t *testing.T) {
	srv, s := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	e, _ := s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Del",
		EventType: "other", StartAt: futureRFC3339(1), EndAt: futureRFC3339(1)})

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/calendar/events/"+e.ID, nil)
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNoContent {
		t.Fatalf("want 204, got %d: %s", w.Code, w.Body.String())
	}
}

func TestHTTP_UpcomingEvents(t *testing.T) {
	srv, s := newTestServer(t)
	mux := http.NewServeMux()
	srv.Register(mux)

	s.CreateEvent(ctx(), kanban.Event{TenantID: tenant, Title: "Upcoming",
		EventType: "other", StartAt: futureRFC3339(2), EndAt: futureRFC3339(2)})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/calendar/events/upcoming?days=7", nil)
	req.Header.Set("X-Tenant-ID", tenant)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
}

// guard ensures time package is used
var _ = time.Now
