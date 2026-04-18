package kanban

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

// Store provides CRUD operations for columns, cards and events.
type Store struct {
	db *sql.DB
}

// NewStore returns a Store and ensures the schema is present.
func NewStore(db *sql.DB) (*Store, error) {
	if err := EnsureSchema(db); err != nil {
		return nil, fmt.Errorf("kanban schema: %w", err)
	}
	return &Store{db: db}, nil
}

// ── Column operations ─────────────────────────────────────────────────────────

// InitTenant inserts the default columns for a tenant if none exist.
func (s *Store) InitTenant(ctx context.Context, tenantID string) error {
	var count int
	s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM crm_kanban_columns WHERE tenant_id=?`, tenantID).Scan(&count)
	if count > 0 {
		return nil
	}
	cols := DefaultColumns(tenantID)
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, c := range cols {
		isDefaultInt := 0
		if c.IsDefault {
			isDefaultInt = 1
		}
		_, err := tx.ExecContext(ctx, `
			INSERT INTO crm_kanban_columns
				(id, tenant_id, name, position, color, vehicle_limit, is_default, state_key, created_at, updated_at)
			VALUES (?,?,?,?,?,?,?,?,?,?)`,
			c.ID, c.TenantID, c.Name, c.Position, c.Color,
			c.VehicleLimit, isDefaultInt, c.StateKey, c.CreatedAt, c.UpdatedAt)
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}

// ListColumns returns all columns for a tenant, each populated with its cards.
func (s *Store) ListColumns(ctx context.Context, tenantID string) ([]Column, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, name, position, color, vehicle_limit, is_default, COALESCE(state_key,''), created_at, updated_at
		FROM crm_kanban_columns WHERE tenant_id=? ORDER BY position`, tenantID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var cols []Column
	for rows.Next() {
		var c Column
		var isDefault int
		if err := rows.Scan(&c.ID, &c.Name, &c.Position, &c.Color,
			&c.VehicleLimit, &isDefault, &c.StateKey, &c.CreatedAt, &c.UpdatedAt); err != nil {
			return nil, err
		}
		c.TenantID = tenantID
		c.IsDefault = isDefault == 1
		cols = append(cols, c)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for i := range cols {
		cards, err := s.listCards(ctx, tenantID, cols[i].ID)
		if err != nil {
			return nil, err
		}
		cols[i].Cards = cards
	}
	return cols, nil
}

// CreateColumn inserts a new custom column for a tenant.
func (s *Store) CreateColumn(ctx context.Context, tenantID, name, color string, vehicleLimit, position int) (Column, error) {
	if strings.TrimSpace(name) == "" {
		return Column{}, fmt.Errorf("column name is required")
	}
	if !strings.HasPrefix(color, "#") || len(color) != 7 {
		color = "#6B7280"
	}
	now := nowRFC3339()
	col := Column{
		ID: newID(), TenantID: tenantID, Name: name,
		Color: color, VehicleLimit: vehicleLimit, Position: position,
		CreatedAt: now, UpdatedAt: now,
	}
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO crm_kanban_columns (id, tenant_id, name, position, color, vehicle_limit, is_default, created_at, updated_at)
		VALUES (?,?,?,?,?,?,0,?,?)`,
		col.ID, col.TenantID, col.Name, col.Position, col.Color, col.VehicleLimit, now, now)
	if err != nil {
		return Column{}, fmt.Errorf("create column: %w", err)
	}
	return col, nil
}

// PatchColumn updates mutable fields on a column.
func (s *Store) PatchColumn(ctx context.Context, tenantID, columnID string, patch ColumnPatch) (Column, error) {
	var sets []string
	var args []any
	if patch.Name != nil {
		sets = append(sets, "name=?")
		args = append(args, *patch.Name)
	}
	if patch.Color != nil {
		sets = append(sets, "color=?")
		args = append(args, *patch.Color)
	}
	if patch.VehicleLimit != nil {
		sets = append(sets, "vehicle_limit=?")
		args = append(args, *patch.VehicleLimit)
	}
	if len(sets) == 0 {
		return s.getColumn(ctx, tenantID, columnID)
	}
	sets = append(sets, "updated_at=?")
	args = append(args, nowRFC3339())
	args = append(args, tenantID, columnID)
	res, err := s.db.ExecContext(ctx,
		"UPDATE crm_kanban_columns SET "+strings.Join(sets, ", ")+" WHERE tenant_id=? AND id=?",
		args...)
	if err != nil {
		return Column{}, err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return Column{}, fmt.Errorf("column not found")
	}
	return s.getColumn(ctx, tenantID, columnID)
}

func (s *Store) getColumn(ctx context.Context, tenantID, columnID string) (Column, error) {
	var c Column
	var isDefault int
	err := s.db.QueryRowContext(ctx, `
		SELECT id, name, position, color, vehicle_limit, is_default, COALESCE(state_key,''), created_at, updated_at
		FROM crm_kanban_columns WHERE tenant_id=? AND id=?`, tenantID, columnID).
		Scan(&c.ID, &c.Name, &c.Position, &c.Color, &c.VehicleLimit, &isDefault, &c.StateKey, &c.CreatedAt, &c.UpdatedAt)
	if err == sql.ErrNoRows {
		return Column{}, fmt.Errorf("column not found")
	}
	c.TenantID = tenantID
	c.IsDefault = isDefault == 1
	return c, err
}

// ── Card operations ───────────────────────────────────────────────────────────

func (s *Store) listCards(ctx context.Context, tenantID, columnID string) ([]Card, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT vehicle_id, column_id, position, COALESCE(assignee_id,''), priority,
		       labels, COALESCE(due_date,''), updated_at
		FROM crm_kanban_cards
		WHERE tenant_id=? AND column_id=? ORDER BY position`, tenantID, columnID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var cards []Card
	for rows.Next() {
		var c Card
		var labelsJSON string
		if err := rows.Scan(&c.VehicleID, &c.ColumnID, &c.Position, &c.AssigneeID,
			&c.Priority, &labelsJSON, &c.DueDate, &c.UpdatedAt); err != nil {
			return nil, err
		}
		c.TenantID = tenantID
		json.Unmarshal([]byte(labelsJSON), &c.Labels)
		if c.Labels == nil {
			c.Labels = []string{}
		}
		cards = append(cards, c)
	}
	return cards, rows.Err()
}

// EnsureCard upserts a card for a vehicle into the correct column.
func (s *Store) EnsureCard(ctx context.Context, tenantID, vehicleID, columnID string, position int) error {
	now := nowRFC3339()
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO crm_kanban_cards (vehicle_id, tenant_id, column_id, position, priority, labels, updated_at)
		VALUES (?,?,?,?,'normal','[]',?)
		ON CONFLICT(vehicle_id) DO UPDATE SET
			column_id=excluded.column_id, position=excluded.position, updated_at=excluded.updated_at`,
		vehicleID, tenantID, columnID, position, now)
	return err
}

// MoveCard moves a vehicle card to a new column, validating the state machine.
// It also updates the vehicle status in crm_vehicles when state_key changes.
func (s *Store) MoveCard(ctx context.Context, tenantID, vehicleID string, req MoveRequest) (Card, error) {
	// Load current card.
	var current Card
	var labelsJSON string
	err := s.db.QueryRowContext(ctx, `
		SELECT vehicle_id, column_id, position, COALESCE(assignee_id,''), priority,
		       labels, COALESCE(due_date,''), updated_at
		FROM crm_kanban_cards WHERE tenant_id=? AND vehicle_id=?`, tenantID, vehicleID).
		Scan(&current.VehicleID, &current.ColumnID, &current.Position, &current.AssigneeID,
			&current.Priority, &labelsJSON, &current.DueDate, &current.UpdatedAt)
	if err == sql.ErrNoRows {
		return Card{}, fmt.Errorf("card not found for vehicle %q", vehicleID)
	}
	if err != nil {
		return Card{}, err
	}
	json.Unmarshal([]byte(labelsJSON), &current.Labels)
	current.TenantID = tenantID

	// Load source and target column state keys.
	srcKey, dstKey, err := s.columnStateKeys(ctx, tenantID, current.ColumnID, req.TargetColumnID)
	if err != nil {
		return Card{}, err
	}

	// Validate transition only when both columns have state keys.
	if srcKey != "" && dstKey != "" && srcKey != dstKey {
		if err := ValidateTransition(srcKey, dstKey); err != nil {
			return Card{}, err
		}
	}

	// Enforce WIP limit on target column.
	var limit int
	s.db.QueryRowContext(ctx, `SELECT vehicle_limit FROM crm_kanban_columns WHERE tenant_id=? AND id=?`,
		tenantID, req.TargetColumnID).Scan(&limit)
	if limit > 0 {
		var count int
		s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM crm_kanban_cards WHERE tenant_id=? AND column_id=?`,
			tenantID, req.TargetColumnID).Scan(&count)
		if count >= limit {
			return Card{}, fmt.Errorf("WIP limit of %d reached for target column", limit)
		}
	}

	now := nowRFC3339()
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Card{}, err
	}
	defer tx.Rollback()

	_, err = tx.ExecContext(ctx, `
		UPDATE crm_kanban_cards SET column_id=?, position=?, updated_at=?
		WHERE tenant_id=? AND vehicle_id=?`,
		req.TargetColumnID, req.Position, now, tenantID, vehicleID)
	if err != nil {
		return Card{}, err
	}

	// Sync vehicle status when state_key is present.
	if dstKey != "" {
		tx.ExecContext(ctx,
			`UPDATE crm_vehicles SET status=?, updated_at=? WHERE tenant_id=? AND id=?`,
			dstKey, now, tenantID, vehicleID)
	}

	if err := tx.Commit(); err != nil {
		return Card{}, err
	}

	metricKanbanMoves.WithLabelValues(tenantID, srcKey, dstKey).Inc()
	current.ColumnID = req.TargetColumnID
	current.Position = req.Position
	current.UpdatedAt = now
	return current, nil
}

// PatchCard updates metadata fields on a card.
func (s *Store) PatchCard(ctx context.Context, tenantID, vehicleID string, patch CardPatch) (Card, error) {
	var sets []string
	var args []any
	if patch.AssigneeID != nil {
		sets = append(sets, "assignee_id=?")
		args = append(args, *patch.AssigneeID)
	}
	if patch.Priority != nil {
		if !ValidPriorities[*patch.Priority] {
			return Card{}, fmt.Errorf("invalid priority %q", *patch.Priority)
		}
		sets = append(sets, "priority=?")
		args = append(args, *patch.Priority)
	}
	if patch.Labels != nil {
		b, _ := json.Marshal(patch.Labels)
		sets = append(sets, "labels=?")
		args = append(args, string(b))
	}
	if patch.DueDate != nil {
		sets = append(sets, "due_date=?")
		args = append(args, *patch.DueDate)
	}
	if len(sets) == 0 {
		return s.getCard(ctx, tenantID, vehicleID)
	}
	sets = append(sets, "updated_at=?")
	args = append(args, nowRFC3339())
	args = append(args, tenantID, vehicleID)
	res, err := s.db.ExecContext(ctx,
		"UPDATE crm_kanban_cards SET "+strings.Join(sets, ", ")+" WHERE tenant_id=? AND vehicle_id=?",
		args...)
	if err != nil {
		return Card{}, err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return Card{}, fmt.Errorf("card not found")
	}
	return s.getCard(ctx, tenantID, vehicleID)
}

func (s *Store) getCard(ctx context.Context, tenantID, vehicleID string) (Card, error) {
	var c Card
	var labelsJSON string
	err := s.db.QueryRowContext(ctx, `
		SELECT vehicle_id, column_id, position, COALESCE(assignee_id,''), priority,
		       labels, COALESCE(due_date,''), updated_at
		FROM crm_kanban_cards WHERE tenant_id=? AND vehicle_id=?`, tenantID, vehicleID).
		Scan(&c.VehicleID, &c.ColumnID, &c.Position, &c.AssigneeID,
			&c.Priority, &labelsJSON, &c.DueDate, &c.UpdatedAt)
	if err == sql.ErrNoRows {
		return Card{}, fmt.Errorf("card not found")
	}
	c.TenantID = tenantID
	json.Unmarshal([]byte(labelsJSON), &c.Labels)
	if c.Labels == nil {
		c.Labels = []string{}
	}
	return c, err
}

func (s *Store) columnStateKeys(ctx context.Context, tenantID, srcID, dstID string) (srcKey, dstKey string, err error) {
	err = s.db.QueryRowContext(ctx,
		`SELECT COALESCE(state_key,'') FROM crm_kanban_columns WHERE tenant_id=? AND id=?`,
		tenantID, srcID).Scan(&srcKey)
	if err == sql.ErrNoRows {
		return "", "", fmt.Errorf("source column not found")
	}
	if err != nil {
		return
	}
	err = s.db.QueryRowContext(ctx,
		`SELECT COALESCE(state_key,'') FROM crm_kanban_columns WHERE tenant_id=? AND id=?`,
		tenantID, dstID).Scan(&dstKey)
	if err == sql.ErrNoRows {
		return "", "", fmt.Errorf("target column not found")
	}
	return
}

// ── Event operations ──────────────────────────────────────────────────────────

// CreateEvent inserts a new calendar event.
func (s *Store) CreateEvent(ctx context.Context, e Event) (Event, error) {
	if strings.TrimSpace(e.Title) == "" {
		return Event{}, fmt.Errorf("event title is required")
	}
	if e.StartAt == "" || e.EndAt == "" {
		return Event{}, fmt.Errorf("start_at and end_at are required")
	}
	if !ValidEventTypes[e.EventType] {
		e.EventType = "other"
	}
	if e.Status == "" {
		e.Status = "scheduled"
	}
	e.ID = newID()
	now := nowRFC3339()
	e.CreatedAt = now
	e.UpdatedAt = now
	allDay := 0
	if e.AllDay {
		allDay = 1
	}
	autoGen := 0
	if e.AutoGenerated {
		autoGen = 1
	}
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO crm_events
			(id, tenant_id, title, description, event_type, vehicle_id, contact_id, deal_id,
			 start_at, end_at, all_day, location, assignee_id, status, reminder_minutes,
			 auto_generated, created_at, updated_at)
		VALUES (?,?,?,?,?,NULLIF(?,  ''),NULLIF(?,''),NULLIF(?,''),?,?,?,?,NULLIF(?,''),?,?,?,?,?)`,
		e.ID, e.TenantID, e.Title, e.Description, e.EventType,
		e.VehicleID, e.ContactID, e.DealID,
		e.StartAt, e.EndAt, allDay, e.Location, e.AssigneeID,
		e.Status, e.ReminderMinutes, autoGen, now, now)
	if err != nil {
		return Event{}, fmt.Errorf("create event: %w", err)
	}
	metricCalendarEvents.WithLabelValues(e.TenantID, e.EventType).Inc()
	return e, nil
}

// ListEvents returns events for a tenant in [from, to] start_at range.
func (s *Store) ListEvents(ctx context.Context, tenantID, from, to string) ([]Event, error) {
	query := `
		SELECT id, title, description, event_type,
		       COALESCE(vehicle_id,''), COALESCE(contact_id,''), COALESCE(deal_id,''),
		       start_at, end_at, all_day, location, COALESCE(assignee_id,''),
		       status, reminder_minutes, auto_generated, created_at, updated_at
		FROM crm_events WHERE tenant_id=? AND status != 'cancelled'`
	args := []any{tenantID}
	if from != "" {
		query += " AND start_at >= ?"
		args = append(args, from)
	}
	if to != "" {
		query += " AND start_at <= ?"
		args = append(args, to)
	}
	query += " ORDER BY start_at"
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanEvents(tenantID, rows)
}

// UpcomingEvents returns events starting in the next [days] days.
func (s *Store) UpcomingEvents(ctx context.Context, tenantID string, days int) ([]Event, error) {
	if days <= 0 {
		days = 7
	}
	from := nowRFC3339()
	to := addDays(from, days)
	return s.ListEvents(ctx, tenantID, from, to)
}

// PatchEvent updates mutable fields on an event.
func (s *Store) PatchEvent(ctx context.Context, tenantID, eventID string, patch EventPatch) (Event, error) {
	var sets []string
	var args []any
	if patch.Title != nil {
		sets = append(sets, "title=?")
		args = append(args, *patch.Title)
	}
	if patch.Description != nil {
		sets = append(sets, "description=?")
		args = append(args, *patch.Description)
	}
	if patch.StartAt != nil {
		sets = append(sets, "start_at=?")
		args = append(args, *patch.StartAt)
	}
	if patch.EndAt != nil {
		sets = append(sets, "end_at=?")
		args = append(args, *patch.EndAt)
	}
	if patch.AllDay != nil {
		v := 0
		if *patch.AllDay {
			v = 1
		}
		sets = append(sets, "all_day=?")
		args = append(args, v)
	}
	if patch.Location != nil {
		sets = append(sets, "location=?")
		args = append(args, *patch.Location)
	}
	if patch.AssigneeID != nil {
		sets = append(sets, "assignee_id=?")
		args = append(args, *patch.AssigneeID)
	}
	if patch.Status != nil {
		sets = append(sets, "status=?")
		args = append(args, *patch.Status)
	}
	if patch.ReminderMinutes != nil {
		sets = append(sets, "reminder_minutes=?")
		args = append(args, *patch.ReminderMinutes)
	}
	if len(sets) == 0 {
		return s.getEvent(ctx, tenantID, eventID)
	}
	sets = append(sets, "updated_at=?")
	args = append(args, nowRFC3339())
	args = append(args, tenantID, eventID)
	res, err := s.db.ExecContext(ctx,
		"UPDATE crm_events SET "+strings.Join(sets, ", ")+" WHERE tenant_id=? AND id=?",
		args...)
	if err != nil {
		return Event{}, err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return Event{}, fmt.Errorf("event not found")
	}
	return s.getEvent(ctx, tenantID, eventID)
}

// CancelEvent sets status=cancelled on an event.
func (s *Store) CancelEvent(ctx context.Context, tenantID, eventID string) error {
	res, err := s.db.ExecContext(ctx,
		`UPDATE crm_events SET status='cancelled', updated_at=? WHERE tenant_id=? AND id=?`,
		nowRFC3339(), tenantID, eventID)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return fmt.Errorf("event not found")
	}
	return nil
}

// OnVehicleStateChange generates automatic calendar events when a vehicle
// transitions to specific states.
func (s *Store) OnVehicleStateChange(ctx context.Context, tenantID, vehicleID, newState string) error {
	now := nowRFC3339()
	switch newState {
	case "in_transit":
		// Estimated delivery in 3 days.
		start := addDays(now, 3)
		_, err := s.CreateEvent(ctx, Event{
			TenantID:      tenantID,
			Title:         "Transport Delivery (estimated)",
			EventType:     "transport_delivery",
			VehicleID:     vehicleID,
			StartAt:       start,
			EndAt:         addDays(start, 0),
			Status:        "scheduled",
			AutoGenerated: true,
		})
		return err
	case "reserved":
		// Registration appointment in 5 days.
		start := addDays(now, 5)
		_, err := s.CreateEvent(ctx, Event{
			TenantID:      tenantID,
			Title:         "Vehicle Registration",
			EventType:     "registration",
			VehicleID:     vehicleID,
			StartAt:       start,
			EndAt:         addDays(start, 0),
			Status:        "scheduled",
			AutoGenerated: true,
		})
		return err
	}
	return nil
}

// RefreshOverdueMetric recomputes the overdue gauge for a tenant.
func (s *Store) RefreshOverdueMetric(ctx context.Context, tenantID string) {
	var count int
	s.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM crm_events
		WHERE tenant_id=? AND status='scheduled' AND end_at < ?`,
		tenantID, nowRFC3339()).Scan(&count)
	metricCalendarOverdue.WithLabelValues(tenantID).Set(float64(count))
}

// WIPGaugeRefresh refreshes the WIP gauge for all columns of a tenant.
func (s *Store) WIPGaugeRefresh(ctx context.Context, tenantID string) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT column_id, COUNT(*) FROM crm_kanban_cards WHERE tenant_id=? GROUP BY column_id`, tenantID)
	if err != nil {
		return
	}
	defer rows.Close()
	for rows.Next() {
		var colID string
		var count int
		if rows.Scan(&colID, &count) == nil {
			metricKanbanWIP.WithLabelValues(tenantID, colID).Set(float64(count))
		}
	}
}

func (s *Store) getEvent(ctx context.Context, tenantID, eventID string) (Event, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, title, description, event_type,
		       COALESCE(vehicle_id,''), COALESCE(contact_id,''), COALESCE(deal_id,''),
		       start_at, end_at, all_day, location, COALESCE(assignee_id,''),
		       status, reminder_minutes, auto_generated, created_at, updated_at
		FROM crm_events WHERE tenant_id=? AND id=?`, tenantID, eventID)
	if err != nil {
		return Event{}, err
	}
	defer rows.Close()
	events, err := scanEvents(tenantID, rows)
	if err != nil {
		return Event{}, err
	}
	if len(events) == 0 {
		return Event{}, fmt.Errorf("event not found")
	}
	return events[0], nil
}

func scanEvents(tenantID string, rows *sql.Rows) ([]Event, error) {
	var events []Event
	for rows.Next() {
		var e Event
		var allDay, autoGen int
		if err := rows.Scan(&e.ID, &e.Title, &e.Description, &e.EventType,
			&e.VehicleID, &e.ContactID, &e.DealID,
			&e.StartAt, &e.EndAt, &allDay, &e.Location, &e.AssigneeID,
			&e.Status, &e.ReminderMinutes, &autoGen,
			&e.CreatedAt, &e.UpdatedAt); err != nil {
			return nil, err
		}
		e.TenantID = tenantID
		e.AllDay = allDay == 1
		e.AutoGenerated = autoGen == 1
		events = append(events, e)
	}
	return events, rows.Err()
}
