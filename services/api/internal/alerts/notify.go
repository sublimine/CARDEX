package alerts

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/smtp"
	"strings"
	"syscall"
	"time"

	"cardex.eu/api/internal/arbitrage"
)

// SMTPConfig configures email delivery. An empty Host disables email.
type SMTPConfig struct {
	Host string
	Port int
	User string
	Pass string
	From string
}

// Enabled reports whether email delivery is configured.
func (c SMTPConfig) Enabled() bool { return c.Host != "" }

// NotificationPayload is the JSON body posted to an alert webhook.
type NotificationPayload struct {
	AlertID       string                  `json:"alert_id"`
	Make          string                  `json:"make"`
	Model         string                  `json:"model"`
	MinMarginPct  float64                 `json:"min_margin_pct"`
	GeneratedAt   time.Time               `json:"generated_at"`
	Opportunities []arbitrage.Opportunity `json:"opportunities"`
}

// Notifier dispatches alert notifications over webhook and email.
type Notifier struct {
	httpClient *http.Client
	smtp       SMTPConfig
}

// NewNotifier builds a Notifier with an SSRF-hardened HTTP client.
func NewNotifier(smtpCfg SMTPConfig) *Notifier {
	return &Notifier{
		httpClient: ssrfSafeClient(),
		smtp:       smtpCfg,
	}
}

// ssrfSafeClient returns an http.Client whose dialer refuses to connect to
// private, loopback, link-local (incl. cloud metadata 169.254.169.254) or
// unspecified addresses. The Control hook runs after DNS resolution on the
// actual IP, so it also defeats DNS-rebinding. Redirects are blocked so a
// public URL cannot 30x into an internal address.
func ssrfSafeClient() *http.Client {
	dialer := &net.Dialer{
		Timeout:   8 * time.Second,
		KeepAlive: 30 * time.Second,
		Control: func(_, address string, _ syscall.RawConn) error {
			host, _, err := net.SplitHostPort(address)
			if err != nil {
				return fmt.Errorf("ssrf guard: bad address %q", address)
			}
			ip := net.ParseIP(host)
			if ip == nil || !isPublicIP(ip) {
				return fmt.Errorf("ssrf guard: destination %q is not a public address", host)
			}
			return nil
		},
	}
	return &http.Client{
		Timeout:   10 * time.Second,
		Transport: &http.Transport{DialContext: dialer.DialContext},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse // do not follow redirects
		},
	}
}

// isPublicIP reports whether ip is globally routable (not private/loopback/etc).
func isPublicIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsPrivate() || ip.IsUnspecified() ||
		ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsInterfaceLocalMulticast() {
		return false
	}
	return true
}

// Webhook POSTs the payload as JSON and requires a 2xx response. Each call is
// bounded by a tight deadline so one slow endpoint cannot stall the evaluator.
func (n *Notifier) Webhook(ctx context.Context, url string, payload NotificationPayload) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal webhook payload: %w", err)
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build webhook request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "CardexAlerts/1.0")

	resp, err := n.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("post webhook: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("webhook returned status %d", resp.StatusCode)
	}
	return nil
}

// Email sends a plain-text summary to the recipient. Returns an error if SMTP is
// not configured.
func (n *Notifier) Email(to string, payload NotificationPayload) error {
	if !n.smtp.Enabled() {
		return fmt.Errorf("email delivery not configured (SMTP_HOST unset)")
	}
	subject := fmt.Sprintf("CARDEX arbitrage alert: %s %s (%d opportunities)",
		payload.Make, payload.Model, len(payload.Opportunities))
	msg := buildEmail(n.smtp.From, to, subject, renderBody(payload))

	addr := net.JoinHostPort(n.smtp.Host, fmt.Sprint(n.smtp.Port))
	var auth smtp.Auth
	if n.smtp.User != "" {
		auth = smtp.PlainAuth("", n.smtp.User, n.smtp.Pass, n.smtp.Host)
	}
	if err := smtp.SendMail(addr, auth, n.smtp.From, []string{to}, msg); err != nil {
		return fmt.Errorf("send email: %w", err)
	}
	return nil
}

// buildEmail assembles a minimal RFC 5322 message. Header values are stripped of
// CR/LF to prevent header injection (defense in depth; validation also rejects them).
func buildEmail(from, to, subject, body string) []byte {
	var b strings.Builder
	fmt.Fprintf(&b, "From: %s\r\n", stripCRLF(from))
	fmt.Fprintf(&b, "To: %s\r\n", stripCRLF(to))
	fmt.Fprintf(&b, "Subject: %s\r\n", stripCRLF(subject))
	b.WriteString("MIME-Version: 1.0\r\n")
	b.WriteString("Content-Type: text/plain; charset=utf-8\r\n")
	b.WriteString("\r\n")
	b.WriteString(body)
	return []byte(b.String())
}

// stripCRLF removes carriage returns and line feeds from a header value.
func stripCRLF(s string) string {
	return strings.NewReplacer("\r", "", "\n", "").Replace(s)
}

// renderBody renders a human-readable opportunity summary.
func renderBody(p NotificationPayload) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Cross-border arbitrage opportunities for %s %s\n", p.Make, p.Model)
	fmt.Fprintf(&b, "Minimum margin: %.1f%%   Generated: %s\n\n",
		p.MinMarginPct, p.GeneratedAt.Format(time.RFC1123))
	for i, op := range p.Opportunities {
		fmt.Fprintf(&b, "%d. Buy in %s for €%.0f → sell in %s (market median €%.0f)\n",
			i+1, op.BuyCountry, op.Listing.PriceEUR, op.SellCountry, op.SellMarketP50EUR)
		fmt.Fprintf(&b, "   Net margin: €%.0f (%.1f%%) after landed cost €%.0f\n",
			op.NetMarginEUR, op.MarginPct, op.LandedCost.TotalLandedCostEUR)
		fmt.Fprintf(&b, "   Listing: %s\n\n", op.Listing.SourceURL)
	}
	b.WriteString("— CARDEX Cross-Border Price Intelligence\n")
	return b.String()
}
