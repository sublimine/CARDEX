package inbox

import (
	"context"
	"errors"
	"time"
)

// ErrNotConfigured is returned by adapters that need credentials not yet supplied.
var ErrNotConfigured = errors.New("inbox source not configured: missing credentials")

// EmailConfig holds IMAP connection parameters.
type EmailConfig struct {
	IMAPHost string
	IMAPPort int
	User     string
	Pass     string
	Mailbox  string // default: "INBOX"
}

func (c EmailConfig) valid() bool {
	return c.IMAPHost != "" && c.User != "" && c.Pass != ""
}

// EmailSource is a generic IMAP email poller.
// Real IMAP connectivity requires credentials; returns ErrNotConfigured when absent.
//
// Production integration: replace the Poll stub with a real IMAP client
// (e.g. github.com/emersion/go-imap) reading unseen messages since `since`.
type EmailSource struct {
	name string
	cfg  EmailConfig
}

// NewEmailSource creates a generic IMAP source with a given logical name.
func NewEmailSource(name string, cfg EmailConfig) *EmailSource {
	if cfg.Mailbox == "" {
		cfg.Mailbox = "INBOX"
	}
	return &EmailSource{name: name, cfg: cfg}
}

func (s *EmailSource) Name() string { return s.name }

// Poll returns ErrNotConfigured when credentials are absent.
// When configured, a real IMAP client would connect, search UNSEEN SINCE,
// parse each email into a RawInquiry, and mark messages as seen.
func (s *EmailSource) Poll(_ context.Context, _ time.Time) ([]RawInquiry, error) {
	if !s.cfg.valid() {
		return nil, ErrNotConfigured
	}
	// TODO: implement IMAP polling with go-imap library once credentials are provisioned.
	return nil, nil
}
