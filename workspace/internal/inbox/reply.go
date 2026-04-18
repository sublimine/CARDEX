package inbox

import (
	"context"
	"database/sql"
	"fmt"
	"net/smtp"
	"time"
)

// ReplyEngine sends replies and records them in CRM.
type ReplyEngine struct {
	convs     *ConversationStore
	templates *TemplateStore
	smtpCfg   SMTPConfig
	db        *sql.DB
}

// NewReplyEngine creates a reply engine.
func NewReplyEngine(db *sql.DB, convs *ConversationStore, templates *TemplateStore, smtpCfg SMTPConfig) *ReplyEngine {
	return &ReplyEngine{
		convs:     convs,
		templates: templates,
		smtpCfg:   smtpCfg,
		db:        db,
	}
}

// Reply sends an outbound message on a conversation.
//   - If req.TemplateID is set, subject/body come from the rendered template.
//   - If req.SendVia == "email", sends via SMTP.
//   - Always creates a crm_messages (outbound) record.
//   - Marks conversation status=replied and unread=0.
func (r *ReplyEngine) Reply(ctx context.Context, tenantID, convID string, req ReplyRequest) (*Message, error) {
	conv, msgs, err := r.convs.Get(tenantID, convID)
	if err != nil {
		return nil, err
	}

	body := req.Body
	subject := ""

	// Resolve template if provided.
	if req.TemplateID != "" {
		tmpl, err := r.templates.GetByID(ctx, tenantID, req.TemplateID)
		if err != nil {
			return nil, fmt.Errorf("template: %w", err)
		}
		subject, body = Render(tmpl, map[string]string{
			"name": r.contactName(ctx, conv.ContactID),
		})
		if req.Body != "" {
			body = req.Body // caller override
		}
	}

	// Find recipient email from last inbound message.
	toEmail := ""
	for i := len(msgs) - 1; i >= 0; i-- {
		if msgs[i].Direction == "inbound" && msgs[i].SenderEmail != "" {
			toEmail = msgs[i].SenderEmail
			if subject == "" {
				subject = "Re: " + conv.Subject
			}
			break
		}
	}

	if req.SendVia == "email" {
		if toEmail == "" {
			return nil, fmt.Errorf("no inbound email address found for conversation %s", convID)
		}
		if err := r.sendEmail(toEmail, subject, body); err != nil {
			return nil, fmt.Errorf("smtp: %w", err)
		}
	}

	msg := &Message{
		ID:             newID(),
		ConversationID: convID,
		Direction:      "outbound",
		Body:           body,
		TemplateID:     req.TemplateID,
		SentVia:        req.SendVia,
		SentAt:         time.Now().UTC(),
		CreatedAt:      time.Now().UTC(),
	}
	if err := r.convs.AddMessage(ctx, msg, "replied"); err != nil {
		return nil, fmt.Errorf("add message: %w", err)
	}

	// Activity: reply.
	r.createReplyActivity(ctx, tenantID, conv.DealID, body)

	RecordMessage("outbound")
	if len(msgs) == 0 {
		// First reply: record response time (0s since we have no inbound time).
	} else {
		for _, m := range msgs {
			if m.Direction == "inbound" {
				RecordResponseTime(time.Since(m.SentAt).Seconds())
				break
			}
		}
	}

	return msg, nil
}

func (r *ReplyEngine) sendEmail(to, subject, body string) error {
	if r.smtpCfg.Host == "" {
		return fmt.Errorf("SMTP not configured")
	}
	addr := fmt.Sprintf("%s:%d", r.smtpCfg.Host, r.smtpCfg.Port)
	auth := smtp.PlainAuth("", r.smtpCfg.User, r.smtpCfg.Pass, r.smtpCfg.Host)
	msg := []byte(
		"To: " + to + "\r\n" +
			"From: " + r.smtpCfg.From + "\r\n" +
			"Subject: " + subject + "\r\n" +
			"Content-Type: text/plain; charset=UTF-8\r\n" +
			"\r\n" +
			body + "\r\n",
	)
	return smtp.SendMail(addr, auth, r.smtpCfg.From, []string{to}, msg)
}

func (r *ReplyEngine) contactName(ctx context.Context, contactID string) string {
	var name string
	_ = r.db.QueryRowContext(ctx, `SELECT name FROM crm_contacts WHERE id=?`, contactID).Scan(&name)
	return name
}

func (r *ReplyEngine) createReplyActivity(ctx context.Context, tenantID, dealID, body string) {
	if dealID == "" {
		return
	}
	_, _ = r.db.ExecContext(ctx,
		`INSERT INTO crm_activities(id,tenant_id,deal_id,type,body,created_at) VALUES(?,?,?,?,?,?)`,
		newID(), tenantID, dealID, "reply", body, time.Now().UTC().Format(time.RFC3339))
}
