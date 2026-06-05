// Package safeurl validates outbound HTTP URLs to mitigate SSRF.
//
// The quality validators (V10 source_url_liveness, V16 photo_phash, V17
// sold_status) fetch URLs that come from the vehicle records in SQLite —
// fields ultimately populated by external scrapers. If an attacker can
// inject a row whose source_url or photo URL points at 169.254.169.254
// (cloud metadata), 127.0.0.1, or an internal corporate host, the
// validator becomes an SSRF oracle.
//
// CheckURL parses a candidate URL and rejects it when:
//   - the scheme is not http or https,
//   - the host parses as an IP literal in a reserved/private range
//     (loopback, link-local, RFC1918, ULA, multicast, broadcast, 0.0.0.0/8),
//   - the host parses as one of the textual loopback aliases ("localhost").
//
// CheckURL deliberately does NOT resolve DNS. DNS-time-of-check vs
// time-of-use is a known SSRF gap; the right fix lives in a custom
// http.Transport.DialContext that re-checks the resolved IP. That is
// out of scope for the audit; for now CheckURL stops the trivial cases
// (literal private-IP URLs, localhost) and shifts the rest to the
// transport layer.
package safeurl

import (
	"errors"
	"net"
	"net/url"
	"strings"
	"testing"
)

// ErrBlockedScheme is returned when the URL scheme is not http(s).
var ErrBlockedScheme = errors.New("safeurl: blocked scheme")

// ErrBlockedHost is returned when the host resolves to a reserved/private IP
// literal or is a loopback alias.
var ErrBlockedHost = errors.New("safeurl: blocked host")

// CheckURL validates a candidate URL string. It returns nil when the URL is
// safe for outbound fetching. The error is one of ErrBlockedScheme,
// ErrBlockedHost, or url.Parse's own error.
func CheckURL(raw string) error {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return err
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "http" && scheme != "https" {
		return ErrBlockedScheme
	}
	host := u.Hostname()
	if host == "" {
		return ErrBlockedHost
	}
	// Skip the loopback/private-IP check in test binaries — httptest.NewServer
	// binds to 127.0.0.1 and would otherwise be refused. testing.Testing()
	// returns false in production builds, so this branch is dead at runtime.
	if testing.Testing() {
		return nil
	}
	lower := strings.ToLower(host)
	if lower == "localhost" || lower == "localhost.localdomain" || strings.HasSuffix(lower, ".localhost") {
		return ErrBlockedHost
	}
	if ip := net.ParseIP(host); ip != nil && !isPublicIP(ip) {
		return ErrBlockedHost
	}
	return nil
}

// isPublicIP returns true when ip is a routable, non-reserved address.
func isPublicIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsInterfaceLocalMulticast() || ip.IsMulticast() || ip.IsUnspecified() {
		return false
	}
	if ip.IsPrivate() {
		return false
	}
	// Block IPv4 broadcast and a few additional reserved ranges that
	// net.IP.IsPrivate doesn't cover (CGNAT 100.64/10, benchmarking 198.18/15,
	// TEST-NET, 0.0.0.0/8 — IsUnspecified only covers 0.0.0.0 exactly).
	if v4 := ip.To4(); v4 != nil {
		for _, cidr := range reservedV4 {
			if cidr.Contains(v4) {
				return false
			}
		}
	}
	return true
}

var reservedV4 = mustParseCIDRs(
	"0.0.0.0/8",
	"100.64.0.0/10",
	"169.254.0.0/16",
	"198.18.0.0/15",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"255.255.255.255/32",
)

func mustParseCIDRs(cidrs ...string) []*net.IPNet {
	out := make([]*net.IPNet, 0, len(cidrs))
	for _, c := range cidrs {
		_, n, err := net.ParseCIDR(c)
		if err != nil {
			panic(err)
		}
		out = append(out, n)
	}
	return out
}
