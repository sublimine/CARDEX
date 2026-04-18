package inbox

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"
)

// Processor converts a RawInquiry into a full set of CRM records atomically.
type Processor struct {
	db *sql.DB
}

// NewProcessor creates a Processor backed by the given DB.
func NewProcessor(db *sql.DB) *Processor {
	return &Processor{db: db}
}

// Process ingests one RawInquiry:
//  1. find-or-create crm_contacts (match by email or phone)
//  2. find crm_vehicles (by external_id, VIN, or fuzzy make+model)
//  3. find-or-create crm_conversations (dedup by source_platform+external_id)
//  4. find-or-create crm_deals (contact+vehicle, stage=lead)
//  5. create crm_activities (type=inquiry)
//  6. create crm_messages (inbound)
//  7. transition vehicle status listed→inquiry
func (p *Processor) Process(ctx context.Context, tenantID string, raw RawInquiry) (*Conversation, error) {
	tx, err := p.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback() //nolint:errcheck

	now := time.Now().UTC()
	nowStr := now.Format(time.RFC3339)

	contact, err := findOrCreateContact(ctx, tx, tenantID, raw.SenderName, raw.SenderEmail, raw.SenderPhone, nowStr)
	if err != nil {
		return nil, fmt.Errorf("contact: %w", err)
	}

	vehicle, err := findVehicle(ctx, tx, tenantID, raw.VehicleRef)
	if err != nil {
		return nil, fmt.Errorf("vehicle: %w", err)
	}

	conv, created, err := findOrCreateConversation(ctx, tx, tenantID, contact.ID, vehicle, raw, nowStr)
	if err != nil {
		return nil, fmt.Errorf("conversation: %w", err)
	}
	if !created {
		// Duplicate inquiry — add message but do not create new deal/activity.
		msg := &Message{
			ID:             newID(),
			ConversationID: conv.ID,
			Direction:      "inbound",
			SenderName:     raw.SenderName,
			SenderEmail:    raw.SenderEmail,
			Body:           raw.Body,
			SentVia:        "platform_reply",
			SentAt:         raw.ReceivedAt,
			CreatedAt:      now,
		}
		if err := insertMessage(ctx, tx, msg); err != nil {
			return nil, fmt.Errorf("dup message: %w", err)
		}
		if err := updateConversationLastMessage(ctx, tx, conv.ID, raw.ReceivedAt, nowStr); err != nil {
			return nil, fmt.Errorf("dup conv update: %w", err)
		}
		return conv, tx.Commit()
	}

	vehicleID := ""
	if vehicle != nil {
		vehicleID = vehicle.ID
	}

	deal, err := findOrCreateDeal(ctx, tx, tenantID, contact.ID, vehicleID, nowStr)
	if err != nil {
		return nil, fmt.Errorf("deal: %w", err)
	}

	// Link deal to conversation.
	if _, err := tx.ExecContext(ctx, `UPDATE crm_conversations SET deal_id=? WHERE id=?`, deal.ID, conv.ID); err != nil {
		return nil, fmt.Errorf("conv deal link: %w", err)
	}
	conv.DealID = deal.ID

	// Activity: inquiry.
	act := &Activity{
		ID:        newID(),
		TenantID:  tenantID,
		DealID:    deal.ID,
		Type:      "inquiry",
		Body:      raw.Body,
		CreatedAt: now,
	}
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO crm_activities(id,tenant_id,deal_id,type,body,created_at) VALUES(?,?,?,?,?,?)`,
		act.ID, act.TenantID, act.DealID, act.Type, act.Body, nowStr); err != nil {
		return nil, fmt.Errorf("activity: %w", err)
	}

	// Message: inbound.
	msg := &Message{
		ID:             newID(),
		ConversationID: conv.ID,
		Direction:      "inbound",
		SenderName:     raw.SenderName,
		SenderEmail:    raw.SenderEmail,
		Body:           raw.Body,
		SentVia:        "platform_reply",
		SentAt:         raw.ReceivedAt,
		CreatedAt:      now,
	}
	if err := insertMessage(ctx, tx, msg); err != nil {
		return nil, fmt.Errorf("message: %w", err)
	}

	// Transition vehicle status: only "listed" → "inquiry" is valid on first
	// inquiry (mirrors the kanban state machine: listed→inquiry is an allowed
	// edge). Any other current status (inquiry, negotiation, reserved, sold…)
	// means the vehicle is already beyond this stage; skip silently — the
	// inquiry is still recorded, only the state update is omitted.
	if vehicle != nil {
		switch vehicle.Status {
		case "listed":
			if _, err := tx.ExecContext(ctx,
				`UPDATE crm_vehicles SET status='inquiry', updated_at=? WHERE id=?`,
				nowStr, vehicle.ID); err != nil {
				return nil, fmt.Errorf("vehicle transition listed→inquiry: %w", err)
			}
		case "inquiry", "negotiation", "reserved", "sold", "in_transit", "delivered":
			// Vehicle already past listing stage — inquiry recorded, no state change.
		default:
			// Unexpected status (e.g. "sourcing", "acquired", "reconditioning"):
			// vehicle is not yet listed, so an external inquiry arriving is anomalous.
			// Record the inquiry but do NOT alter vehicle status to avoid corruption.
		}
	}

	RecordConversation("open", raw.SourcePlatform)
	RecordMessage("inbound")

	return conv, tx.Commit()
}

// ── helpers ────────────────────────────────────────────────────────────────────

func findOrCreateContact(ctx context.Context, tx *sql.Tx, tenantID, name, email, phone, nowStr string) (*Contact, error) {
	c := &Contact{TenantID: tenantID}

	scanContact := func(row *sql.Row) (bool, error) {
		var createdStr string
		err := row.Scan(&c.ID, &c.Name, &c.Email, &c.Phone, &createdStr)
		if err == sql.ErrNoRows {
			return false, nil
		}
		if err != nil {
			return false, err
		}
		c.CreatedAt, _ = time.Parse(time.RFC3339, createdStr)
		return true, nil
	}

	// Try email first, then phone.
	if email != "" {
		found, err := scanContact(tx.QueryRowContext(ctx,
			`SELECT id,name,email,phone,created_at FROM crm_contacts WHERE tenant_id=? AND email=? LIMIT 1`,
			tenantID, email))
		if err != nil {
			return nil, err
		}
		if found {
			return c, nil
		}
	}
	if phone != "" {
		found, err := scanContact(tx.QueryRowContext(ctx,
			`SELECT id,name,email,phone,created_at FROM crm_contacts WHERE tenant_id=? AND phone=? LIMIT 1`,
			tenantID, phone))
		if err != nil {
			return nil, err
		}
		if found {
			return c, nil
		}
	}

	// Create.
	c.ID = newID()
	c.Name = name
	c.Email = email
	c.Phone = phone
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO crm_contacts(id,tenant_id,name,email,phone,created_at,updated_at) VALUES(?,?,?,?,?,?,?)`,
		c.ID, tenantID, name, email, phone, nowStr, nowStr); err != nil {
		return nil, err
	}
	return c, nil
}

// findVehicle attempts a lookup by external_id, VIN, then fuzzy make+model.
// Returns nil (no error) when no match is found — a new vehicle won't be created from inquiry data alone.
func findVehicle(ctx context.Context, tx *sql.Tx, tenantID, ref string) (*Vehicle, error) {
	if ref == "" {
		return nil, nil
	}
	v := &Vehicle{TenantID: tenantID}

	// external_id exact match
	err := tx.QueryRowContext(ctx,
		`SELECT id,external_id,vin,make,model,year,status FROM crm_vehicles WHERE tenant_id=? AND external_id=? LIMIT 1`,
		tenantID, ref).Scan(&v.ID, &v.ExternalID, &v.VIN, &v.Make, &v.Model, &v.Year, &v.Status)
	if err == nil {
		return v, nil
	}

	// VIN exact match
	err = tx.QueryRowContext(ctx,
		`SELECT id,external_id,vin,make,model,year,status FROM crm_vehicles WHERE tenant_id=? AND vin=? LIMIT 1`,
		tenantID, ref).Scan(&v.ID, &v.ExternalID, &v.VIN, &v.Make, &v.Model, &v.Year, &v.Status)
	if err == nil {
		return v, nil
	}

	// Fuzzy: "Make Model Year" split
	parts := strings.Fields(ref)
	if len(parts) >= 2 {
		make_ := parts[0]
		model := parts[1]
		err = tx.QueryRowContext(ctx,
			`SELECT id,external_id,vin,make,model,year,status FROM crm_vehicles
			 WHERE tenant_id=? AND LOWER(make)=LOWER(?) AND LOWER(model) LIKE LOWER(?)
			 ORDER BY year DESC LIMIT 1`,
			tenantID, make_, "%"+model+"%").
			Scan(&v.ID, &v.ExternalID, &v.VIN, &v.Make, &v.Model, &v.Year, &v.Status)
		if err == nil {
			return v, nil
		}
	}
	return nil, nil
}

func findOrCreateConversation(ctx context.Context, tx *sql.Tx, tenantID, contactID string, v *Vehicle, raw RawInquiry, nowStr string) (*Conversation, bool, error) {
	c := &Conversation{TenantID: tenantID, ContactID: contactID}
	if v != nil {
		c.VehicleID = v.ID
	}

	// Dedup by external_id + platform
	if raw.ExternalID != "" {
		var unread int
		var lastMsg, created string
		err := tx.QueryRowContext(ctx,
			`SELECT id,COALESCE(vehicle_id,''),COALESCE(deal_id,''),source_platform,status,unread,last_message_at,created_at
			 FROM crm_conversations WHERE tenant_id=? AND source_platform=? AND external_id=?`,
			tenantID, raw.SourcePlatform, raw.ExternalID).
			Scan(&c.ID, &c.VehicleID, &c.DealID, &c.SourcePlatform, &c.Status, &unread, &lastMsg, &created)
		if err == nil {
			c.Unread = unread == 1
			c.LastMessageAt, _ = time.Parse(time.RFC3339, lastMsg)
			c.CreatedAt, _ = time.Parse(time.RFC3339, created)
			return c, false, nil // already exists
		}
		if err != sql.ErrNoRows {
			return nil, false, err
		}
	}

	// Create.
	c.ID = newID()
	c.SourcePlatform = raw.SourcePlatform
	c.ExternalID = raw.ExternalID
	c.Subject = raw.Subject
	c.Status = "open"
	c.Unread = true
	c.LastMessageAt = raw.ReceivedAt
	c.CreatedAt = raw.ReceivedAt

	var extID *string
	if raw.ExternalID != "" {
		extID = &raw.ExternalID
	}
	var vehID *string
	if v != nil {
		vehID = &v.ID
	}

	_, err := tx.ExecContext(ctx,
		`INSERT INTO crm_conversations(id,tenant_id,contact_id,vehicle_id,source_platform,external_id,subject,status,unread,last_message_at,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`,
		c.ID, tenantID, contactID, vehID, raw.SourcePlatform, extID,
		raw.Subject, "open", 1, raw.ReceivedAt.Format(time.RFC3339), nowStr, nowStr)
	if err != nil {
		return nil, false, err
	}
	return c, true, nil
}

func findOrCreateDeal(ctx context.Context, tx *sql.Tx, tenantID, contactID, vehicleID, nowStr string) (*Deal, error) {
	d := &Deal{TenantID: tenantID}

	// Look for open deal with same contact+vehicle.
	var query string
	var args []any
	if vehicleID != "" {
		query = `SELECT id,COALESCE(vehicle_id,''),stage FROM crm_deals WHERE tenant_id=? AND contact_id=? AND vehicle_id=? AND stage NOT IN ('won','lost') LIMIT 1`
		args = []any{tenantID, contactID, vehicleID}
	} else {
		query = `SELECT id,COALESCE(vehicle_id,''),stage FROM crm_deals WHERE tenant_id=? AND contact_id=? AND stage NOT IN ('won','lost') ORDER BY created_at DESC LIMIT 1`
		args = []any{tenantID, contactID}
	}
	err := tx.QueryRowContext(ctx, query, args...).Scan(&d.ID, &d.VehicleID, &d.Stage)
	if err == nil {
		return d, nil
	}
	if err != sql.ErrNoRows {
		return nil, err
	}

	d.ID = newID()
	d.ContactID = contactID
	d.VehicleID = vehicleID
	d.Stage = "lead"
	var vehID *string
	if vehicleID != "" {
		vehID = &vehicleID
	}
	_, err = tx.ExecContext(ctx,
		`INSERT INTO crm_deals(id,tenant_id,contact_id,vehicle_id,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?)`,
		d.ID, tenantID, contactID, vehID, "lead", nowStr, nowStr)
	return d, err
}

func insertMessage(ctx context.Context, tx *sql.Tx, m *Message) error {
	var templateID *string
	if m.TemplateID != "" {
		templateID = &m.TemplateID
	}
	var readAt *string
	if m.ReadAt != nil {
		s := m.ReadAt.Format(time.RFC3339)
		readAt = &s
	}
	_, err := tx.ExecContext(ctx,
		`INSERT INTO crm_messages(id,conversation_id,direction,sender_name,sender_email,body,template_id,sent_via,sent_at,read_at,created_at)
		 VALUES(?,?,?,?,?,?,?,?,?,?,?)`,
		m.ID, m.ConversationID, m.Direction, m.SenderName, m.SenderEmail,
		m.Body, templateID, m.SentVia, m.SentAt.Format(time.RFC3339), readAt,
		m.CreatedAt.Format(time.RFC3339))
	return err
}

func updateConversationLastMessage(ctx context.Context, tx *sql.Tx, convID string, lastMsg time.Time, nowStr string) error {
	_, err := tx.ExecContext(ctx,
		`UPDATE crm_conversations SET last_message_at=?, unread=1, updated_at=? WHERE id=?`,
		lastMsg.Format(time.RFC3339), nowStr, convID)
	return err
}
