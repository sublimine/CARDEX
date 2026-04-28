package inbox

import (
	"context"
	"crypto/rand"
	"fmt"
	"time"
)

// ── Source interface ──────────────────────────────────────────────────────────

// InquirySource is the polling interface every platform adapter implements.
type InquirySource interface {
	Name() string
	Poll(ctx context.Context, since time.Time) ([]RawInquiry, error)
}

// RawInquiry is the raw, platform-agnostic inquiry before CRM processing.
type RawInquiry struct {
	SourcePlatform string
	ExternalID     string // deduplication key on the originating platform
	VehicleRef     string // external_id, VIN, or "Make Model Year"
	SenderName     string
	SenderEmail    string
	SenderPhone    string
	Subject        string
	Body           string
	ReceivedAt     time.Time
	Metadata       map[string]string
}

// ── CRM entities ─────────────────────────────────────────────────────────────

type Contact struct {
	ID        string
	TenantID  string
	Name      string
	Email     string
	Phone     string
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Vehicle struct {
	ID         string
	TenantID   string
	ExternalID string
	VIN        string
	Make       string
	Model      string
	Year       int
	Status     string // listed|inquiry|sold|withdrawn
	CreatedAt  time.Time
	UpdatedAt  time.Time
}

type Deal struct {
	ID        string
	TenantID  string
	ContactID string
	VehicleID string
	Stage     string // lead|contacted|offer|negotiation|won|lost
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Activity struct {
	ID        string
	TenantID  string
	DealID    string
	Type      string // inquiry|reply|reminder|note|visit|call
	Body      string
	CreatedAt time.Time
}

// ── Inbox entities ────────────────────────────────────────────────────────────

type Conversation struct {
	ID             string
	TenantID       string
	ContactID      string
	VehicleID      string
	DealID         string
	SourcePlatform string
	ExternalID     string
	Subject        string
	Status         string // open|replied|closed|spam
	Unread         bool
	LastMessageAt  time.Time
	CreatedAt      time.Time
	UpdatedAt      time.Time
}

type Message struct {
	ID             string
	ConversationID string
	Direction      string // inbound|outbound
	SenderName     string
	SenderEmail    string
	Body           string
	TemplateID     string
	SentVia        string // email|platform_reply|manual
	SentAt         time.Time
	ReadAt         *time.Time
	CreatedAt      time.Time
}

type Template struct {
	ID        string
	TenantID  string
	Name      string
	Language  string
	Subject   string
	Body      string
	IsSystem  bool
	CreatedAt time.Time
	UpdatedAt time.Time
}

// ── API request/response types ────────────────────────────────────────────────

type ReplyRequest struct {
	Body       string `json:"body"`
	TemplateID string `json:"template_id,omitempty"`
	SendVia    string `json:"send_via"` // email|manual
}

type PatchConversationRequest struct {
	Status *string `json:"status,omitempty"` // closed|spam|open|replied
	Unread *bool   `json:"unread,omitempty"`
}

type ListInboxQuery struct {
	Status    string // open|replied|closed|spam|"" (all non-spam)
	Platform  string
	Unread    *bool
	VehicleID string
	Page      int
	PageSize  int
}

type ConversationWithMessages struct {
	Conversation *Conversation `json:"conversation"`
	Messages     []*Message    `json:"messages"`
}

type SMTPConfig struct {
	Host string
	Port int
	User string
	Pass string
	From string
}

// ── ID generation ─────────────────────────────────────────────────────────────

func newID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
