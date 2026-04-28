package inbox

import (
	"context"
	"database/sql"
	"fmt"
	"time"
)

// ConversationStore provides CRUD for conversations and messages.
type ConversationStore struct {
	db *sql.DB
}

// NewConversationStore creates a store backed by db.
func NewConversationStore(db *sql.DB) *ConversationStore {
	return &ConversationStore{db: db}
}

// List returns paginated conversations for a tenant, applying query filters.
// By default excludes spam unless q.Status == "spam".
func (s *ConversationStore) List(tenantID string, q ListInboxQuery) ([]*Conversation, error) {
	if q.PageSize <= 0 {
		q.PageSize = 20
	}
	offset := q.Page * q.PageSize

	where := "tenant_id = ?"
	args := []any{tenantID}

	if q.Status != "" {
		where += " AND status = ?"
		args = append(args, q.Status)
	} else {
		where += " AND status != 'spam'"
	}

	if q.Platform != "" {
		where += " AND source_platform = ?"
		args = append(args, q.Platform)
	}
	if q.Unread != nil {
		if *q.Unread {
			where += " AND unread = 1"
		} else {
			where += " AND unread = 0"
		}
	}
	if q.VehicleID != "" {
		where += " AND vehicle_id = ?"
		args = append(args, q.VehicleID)
	}

	args = append(args, q.PageSize, offset)
	rows, err := s.db.QueryContext(context.Background(),
		`SELECT id,tenant_id,contact_id,COALESCE(vehicle_id,''),COALESCE(deal_id,''),
		        source_platform,COALESCE(external_id,''),subject,status,unread,
		        last_message_at,created_at,updated_at
		 FROM crm_conversations
		 WHERE `+where+`
		 ORDER BY last_message_at DESC
		 LIMIT ? OFFSET ?`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []*Conversation
	for rows.Next() {
		c, err := scanConversation(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// Get returns a conversation with all its messages, or error if not found.
func (s *ConversationStore) Get(tenantID, id string) (*Conversation, []*Message, error) {
	row := s.db.QueryRowContext(context.Background(),
		`SELECT id,tenant_id,contact_id,COALESCE(vehicle_id,''),COALESCE(deal_id,''),
		        source_platform,COALESCE(external_id,''),subject,status,unread,
		        last_message_at,created_at,updated_at
		 FROM crm_conversations WHERE id=? AND tenant_id=?`, id, tenantID)
	c, err := scanConversationRow(row)
	if err == sql.ErrNoRows {
		return nil, nil, fmt.Errorf("conversation %s not found", id)
	}
	if err != nil {
		return nil, nil, err
	}

	rows, err := s.db.QueryContext(context.Background(),
		`SELECT id,conversation_id,direction,sender_name,sender_email,body,
		        COALESCE(template_id,''),sent_via,sent_at,read_at,created_at
		 FROM crm_messages WHERE conversation_id=? ORDER BY sent_at`, id)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()

	var msgs []*Message
	for rows.Next() {
		m, err := scanMessage(rows)
		if err != nil {
			return nil, nil, err
		}
		msgs = append(msgs, m)
	}
	return c, msgs, rows.Err()
}

// Patch updates status and/or unread flag on a conversation.
func (s *ConversationStore) Patch(tenantID, id string, req PatchConversationRequest) error {
	nowStr := time.Now().UTC().Format(time.RFC3339)
	if req.Status != nil && req.Unread != nil {
		unread := 0
		if *req.Unread {
			unread = 1
		}
		_, err := s.db.ExecContext(context.Background(),
			`UPDATE crm_conversations SET status=?,unread=?,updated_at=? WHERE id=? AND tenant_id=?`,
			*req.Status, unread, nowStr, id, tenantID)
		return err
	}
	if req.Status != nil {
		_, err := s.db.ExecContext(context.Background(),
			`UPDATE crm_conversations SET status=?,updated_at=? WHERE id=? AND tenant_id=?`,
			*req.Status, nowStr, id, tenantID)
		return err
	}
	if req.Unread != nil {
		unread := 0
		if *req.Unread {
			unread = 1
		}
		_, err := s.db.ExecContext(context.Background(),
			`UPDATE crm_conversations SET unread=?,updated_at=? WHERE id=? AND tenant_id=?`,
			unread, nowStr, id, tenantID)
		return err
	}
	return nil
}

// AddMessage inserts an outbound message and updates conversation metadata.
func (s *ConversationStore) AddMessage(ctx context.Context, msg *Message, newStatus string) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback() //nolint:errcheck

	if err := insertMessage(ctx, tx, msg); err != nil {
		return err
	}

	nowStr := time.Now().UTC().Format(time.RFC3339)
	_, err = tx.ExecContext(ctx,
		`UPDATE crm_conversations SET status=?, unread=0, last_message_at=?, updated_at=? WHERE id=?`,
		newStatus, msg.SentAt.Format(time.RFC3339), nowStr, msg.ConversationID)
	if err != nil {
		return err
	}
	return tx.Commit()
}

// ── scanners ──────────────────────────────────────────────────────────────────

type rowScanner interface {
	Scan(dest ...any) error
}

func scanConversation(rs rowScanner) (*Conversation, error) {
	c := &Conversation{}
	var lastMsg, created, updated string
	var unread int
	err := rs.Scan(&c.ID, &c.TenantID, &c.ContactID, &c.VehicleID, &c.DealID,
		&c.SourcePlatform, &c.ExternalID, &c.Subject, &c.Status, &unread,
		&lastMsg, &created, &updated)
	if err != nil {
		return nil, err
	}
	c.Unread = unread == 1
	c.LastMessageAt, _ = time.Parse(time.RFC3339, lastMsg)
	c.CreatedAt, _ = time.Parse(time.RFC3339, created)
	c.UpdatedAt, _ = time.Parse(time.RFC3339, updated)
	return c, nil
}

func scanConversationRow(row *sql.Row) (*Conversation, error) {
	c := &Conversation{}
	var lastMsg, created, updated string
	var unread int
	err := row.Scan(&c.ID, &c.TenantID, &c.ContactID, &c.VehicleID, &c.DealID,
		&c.SourcePlatform, &c.ExternalID, &c.Subject, &c.Status, &unread,
		&lastMsg, &created, &updated)
	if err != nil {
		return nil, err
	}
	c.Unread = unread == 1
	c.LastMessageAt, _ = time.Parse(time.RFC3339, lastMsg)
	c.CreatedAt, _ = time.Parse(time.RFC3339, created)
	c.UpdatedAt, _ = time.Parse(time.RFC3339, updated)
	return c, nil
}

func scanMessage(rs rowScanner) (*Message, error) {
	m := &Message{}
	var sentAt, created string
	var readAt *string
	err := rs.Scan(&m.ID, &m.ConversationID, &m.Direction, &m.SenderName, &m.SenderEmail,
		&m.Body, &m.TemplateID, &m.SentVia, &sentAt, &readAt, &created)
	if err != nil {
		return nil, err
	}
	m.SentAt, _ = time.Parse(time.RFC3339, sentAt)
	m.CreatedAt, _ = time.Parse(time.RFC3339, created)
	if readAt != nil {
		t, _ := time.Parse(time.RFC3339, *readAt)
		m.ReadAt = &t
	}
	return m, nil
}
