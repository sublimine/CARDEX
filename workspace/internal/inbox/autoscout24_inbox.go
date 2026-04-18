package inbox

import (
	"context"
	"strings"
	"time"
)

// AutoScout24Source polls AutoScout24 inquiries via email forwarding.
//
// AutoScout24 forwards inquiry emails to the dealer's registered address.
// Expected sender:  "noreply@autoscout24.com" or "leads@autoscout24.com"
// Expected subject: "New enquiry for your listing: <Make> <Model>"
//                   or "Nouvelle demande de contact: <Make> <Model>" (FR)
//                   or "Nueva solicitud de contacto: <Make> <Model>" (ES)
type AutoScout24Source struct {
	email *EmailSource
}

// NewAutoScout24Source creates an AutoScout24 adapter backed by IMAP credentials.
func NewAutoScout24Source(cfg EmailConfig) *AutoScout24Source {
	return &AutoScout24Source{email: NewEmailSource("autoscout24", cfg)}
}

func (s *AutoScout24Source) Name() string { return "autoscout24" }

// Poll fetches emails and converts AutoScout24 inquiry messages into RawInquiries.
func (s *AutoScout24Source) Poll(ctx context.Context, since time.Time) ([]RawInquiry, error) {
	raw, err := s.email.Poll(ctx, since)
	if err != nil {
		return nil, err
	}
	var out []RawInquiry
	for _, r := range raw {
		if isAutoScout24Inquiry(r) {
			r.SourcePlatform = "autoscout24"
			r.Metadata = parseAutoScout24Metadata(r)
			out = append(out, r)
		}
	}
	return out, nil
}

func isAutoScout24Inquiry(r RawInquiry) bool {
	return strings.Contains(r.SenderEmail, "autoscout24.com") ||
		strings.ContainsAny(r.Subject, "") && (
			strings.Contains(r.Subject, "enquiry") ||
				strings.Contains(r.Subject, "demande de contact") ||
				strings.Contains(r.Subject, "solicitud de contacto"))
}

// parseAutoScout24Metadata extracts listing ID and contact details from AS24 emails.
// Real implementation would parse the structured lead notification HTML body.
func parseAutoScout24Metadata(r RawInquiry) map[string]string {
	meta := map[string]string{"platform": "autoscout24"}
	for _, line := range strings.Split(r.Body, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "Listing ID:") {
			meta["listing_id"] = strings.TrimSpace(strings.TrimPrefix(line, "Listing ID:"))
		}
		if strings.HasPrefix(line, "Offer ID:") {
			meta["offer_id"] = strings.TrimSpace(strings.TrimPrefix(line, "Offer ID:"))
		}
	}
	return meta
}
