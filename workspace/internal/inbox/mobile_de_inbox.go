package inbox

import (
	"context"
	"strings"
	"time"
)

// MobileDeSource polls mobile.de inquiries via email forwarding.
//
// mobile.de sends inquiry notification emails to the dealer's registered address.
// These land in the dealer's IMAP mailbox; this adapter wraps EmailSource and adds
// mobile.de-specific email parsing.
//
// Expected subject pattern: "Anfrage zu Ihrem Inserat: <Make> <Model>"
// Expected sender domain:   "noreply@mobile.de" or "anfragen@mobile.de"
type MobileDeSource struct {
	email *EmailSource
}

// NewMobileDeSource creates a mobile.de adapter backed by IMAP credentials.
func NewMobileDeSource(cfg EmailConfig) *MobileDeSource {
	return &MobileDeSource{email: NewEmailSource("mobile_de", cfg)}
}

func (s *MobileDeSource) Name() string { return "mobile_de" }

// Poll fetches emails via IMAP and converts mobile.de inquiry messages into RawInquiries.
func (s *MobileDeSource) Poll(ctx context.Context, since time.Time) ([]RawInquiry, error) {
	raw, err := s.email.Poll(ctx, since)
	if err != nil {
		return nil, err
	}
	var out []RawInquiry
	for _, r := range raw {
		if isMobileDeInquiry(r) {
			r.SourcePlatform = "mobile_de"
			r.Metadata = parseMobileDeMetadata(r)
			out = append(out, r)
		}
	}
	return out, nil
}

func isMobileDeInquiry(r RawInquiry) bool {
	return strings.Contains(r.SenderEmail, "mobile.de") ||
		strings.Contains(r.Subject, "Anfrage") ||
		strings.Contains(r.Subject, "Inserat")
}

// parseMobileDeMetadata extracts the ad ID from mobile.de notification emails.
// Real implementation would parse the structured HTML/text email body.
func parseMobileDeMetadata(r RawInquiry) map[string]string {
	meta := map[string]string{"platform": "mobile_de"}
	// Pattern: "Inserat-ID: 123456789"
	for _, line := range strings.Split(r.Body, "\n") {
		if strings.HasPrefix(line, "Inserat-ID:") {
			meta["ad_id"] = strings.TrimSpace(strings.TrimPrefix(line, "Inserat-ID:"))
		}
	}
	return meta
}
